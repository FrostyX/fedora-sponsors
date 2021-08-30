#!/usr/bin/python3
# -*- coding: utf-8 -*-
# vim: noai:ts=4:sw=4:expandtab
# Original author: Miroslav Suchý

from fedora.client import AuthError, AccountSystem, ServerError
from six.moves import configparser
from functools import wraps, cached_property
from datetime import datetime, date, timedelta
import time
import xmlrpc
import bugzilla
import getpass
import sys
import os
import six
import requests

from groups import fetch_personal_config


DAYS_AGO = 365 * 2

# TODO This should not be global
DIRECTLY_SPONSORED = {}


class IDtoNameCache:
    """
    Converting `user_id` to FAS username is an expensive operation, therefore
    we want to cache the results and once known usernames simply return from
    memory.

    Maybe we don't need this whole class and can implement an username property
    in `User` class.
    """

    # Cache mapping of user id to name
    map_id_to_name = {}

    @classmethod
    def convert_id_to_name(cls, user_id, client):
        if user_id not in cls.map_id_to_name:
            name = client.person_by_id(user_id).username
            cls.map_id_to_name[user_id] = name
        return cls.map_id_to_name[user_id]


def get_bugs(bz, fas_user):
    """
    Fetch all _recent_ Fedora Review bugs that are assigned to a given FAS user
    """
    query = {
        'query_format': 'advanced',
        'component': 'Package Review',
        'classification': 'Fedora',
        'product': 'Fedora',
        'emailtype1': 'substring',
        'email1': fas_user.bugzilla_email,
        'emailassigned_to1': '1',
        'list_id': '3718380',
        'chfieldto': 'Now',
        'chfieldfrom': '-{0}d'.format(DAYS_AGO),
        'chfield': 'bug_status'
    }
    return bz.query(query)


class User:
    """
    A high-level abstraction for interacting with users.
    """
    def __init__(self, username, client, bz):
        self.username = username
        self.client = client
        self.bz = bz

    @cached_property
    def fas(self):
        return self.client.person_by_username(self.username)

    @cached_property
    def human_name(self):
        return self.fas.human_name

    @cached_property
    def sponsor_config(self):
        return fetch_personal_config(self.username)


def examine_activity_on_bug(user, bug):
    """
    Examine whether a user made any activity on a particular bug and return a
    boolean value.
    """

    history = bug.get_history_raw()
    # 177841 is FE-NEEDSPONSOR
    if 177841 in bug.blocks:
        # check if sponsor changed status of the bug
        for change in history['bugs'][0]['history']:
            if change['when'] > date.today() - timedelta(DAYS_AGO):
                if change['who'] == user.human_name:
                    for i in change['changes']:
                        if 'field_name' in i:
                            print(u"{0} <{1}> worked on BZ {2}".format(user.human_name, user.username, bug.id))
                            return True
                    else:
                        continue # hack to break to outer for-loop if we called break 2 lines above
                    break

    else:
        # check if sponsor removed FE-NEEDSPONSOR in past one year
        for change in history['bugs'][0]['history']:
            if change['when'] > date.today() - timedelta(DAYS_AGO):
                if change['who'] == user.human_name:
                    for i in change['changes']:
                        if 'removed' in i and 'field_name' in i and \
            i['removed'] == '177841' and i['field_name'] == 'blocks':
                            print(u"{0} <{1}> removed FE-NEEDSPONSOR from BZ {2}".format(user.human_name, user.username, bug.id))
                            return True
                    else:
                        continue # hack to break to outer for-loop if we called break 2 lines above
                    break
    return False


def find_directly_sponsored(client):
    """
    Query FAS and find what users were sponsored and by whom.
    """
    packager_group = client.group_by_name("packager")
    for role in packager_group.approved_roles:
        if role.role_type != 'user':
            continue

        date_format = "%Y-%m-%d %H:%M:%S.%f+00:00"
        approved_date = datetime.strptime(role.approval, date_format)
        if approved_date <= datetime.today() - timedelta(DAYS_AGO):
            continue

        DIRECTLY_SPONSORED.setdefault(role.sponsor_id, [])
        DIRECTLY_SPONSORED[role.sponsor_id].append(role.person_id)


def process_user(username, client, bz):
    """
    Did this user do any sponsor activity?
    """
    good_guy = False
    user = User(username, client, bz)
    if user.fas.status != "active":
        return None

    if not user.human_name:
        return None

    # Examine activity in bugzilla
    for bug in get_bugs(bz, user.fas):
        good_guy = examine_activity_on_bug(user, bug)

    # Examine sponsorships in FAS
    if user.fas.id in DIRECTLY_SPONSORED:
        good_guy = True
        sponsored_users = DIRECTLY_SPONSORED[user.fas.id]
        sponsored_users = [IDtoNameCache.convert_id_to_name(u, client)
                           for u in sponsored_users]
        print("{0} <{1}> - directly sponsored: {2}".format(
            user.human_name, user.username, sponsored_users))

    # We may not always discover a sponsor's activity accurately and display
    # somebody as inactive even though he isn't.
    # See https://github.com/FrostyX/fedora-sponsors/issues/13
    #
    # As a workaround let's consider all sponsors that created their sponsor.yaml
    # config on https://fedorapeople.org/ active.
    if user.sponsor_config:
        good_guy = True
        print("{0} <{1}> - has sponsor.yaml on fedorapeople.org"
              .format(user.human_name, user.username))

    if not good_guy:
        print("{0} <{1}> - no recent sponsor activity".format(
            user.human_name, user.username))

    return user.fas if good_guy else False


def process_user_safe(username, client, bz):
    """
    Obtaining person information can fail because temporary network issues or
    server overload. Try again until we get the info successfully.
    """
    try:
        return process_user(username, client, bz)
    except (ServerError, requests.RequestException):
        time.sleep(5)
        return process_user_safe(username, client, bz)


def config_value(raw_config, key):
    try:
        if six.PY3:
            return raw_config["main"].get(key, None)
        else:
            return raw_config.get("main", key, None)
    except configparser.Error as err:
        sys.stderr.write("Bad configuration file: {0}".format(err))
        sys.exit(1)


def dump(good_guys):
    """
    Write active sponsors into an output file
    """
    good_guys_usernames = [sponsor.username for sponsor in good_guys if sponsor]
    here = os.path.dirname(os.path.realpath(__file__))
    dstdir = os.path.join(here, "_build")
    if not os.path.exists(dstdir):
        os.makedirs(dstdir)
    dst = os.path.join(dstdir, "active-sponsors.list")
    with open(dst, "w") as f:
        f.write("\n".join(good_guys_usernames) + "\n")


def main():
    client = AccountSystem()
    bz = bugzilla.Bugzilla(url='https://bugzilla.redhat.com/xmlrpc.cgi')

    raw_config = configparser.ConfigParser()
    filepath = os.path.join(os.path.expanduser("~"), ".config", "fedora")
    config = {}
    if raw_config.read(filepath):
        client.username = config_value(raw_config, "username")
        client.password = config_value(raw_config, "password")

    try:
        packagers = client.group_members("packager")
    except AuthError as e:
        print("Login interactively or create {0}".format(filepath))
        client.username = input('Username: ').strip()
        client.password = getpass.getpass('Password: ')
        packagers = client.group_members("packager")

    sponsors = [s.username for s in packagers if s.role_type == "sponsor"]
    packagers = [p.username for p in packagers]
    find_directly_sponsored(client)

    good_guys = []
    for sponsor in sponsors:
        good_guys.append(process_user_safe(sponsor, client, bz))
    dump(good_guys)


if __name__ == "__main__":
    main()
