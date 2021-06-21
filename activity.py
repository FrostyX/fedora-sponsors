#!/usr/bin/python3
# -*- coding: utf-8 -*-
# vim: noai:ts=4:sw=4:expandtab
# Original author: Miroslav Suchý

from fedora.client import AuthError, AccountSystem, ServerError
from six.moves import configparser
import time
import xmlrpc
import bugzilla
import datetime
import getpass
import os
import six
import requests

DAYS_AGO = 365 * 2
client = AccountSystem()
bz = bugzilla.Bugzilla(url='https://bugzilla.redhat.com/xmlrpc.cgi')

# cache mapping of user id to name
map_id_to_name = {}
def convert_id_to_name(user_id):
    if user_id not in map_id_to_name:
        map_id_to_name[user_id] = get_person_by_id_safe(user_id).username
    return map_id_to_name[user_id]


def get_safely(function, *args, **kwargs):
    """
    Obtaining person information can fail because temporary network issues or
    server overload. Try again until we get the info successfully.
    """
    try:
        return function(*args, **kwargs)
    except (ServerError, requests.HTTPError):
        time.sleep(5)
        return get_safely(*args, **kwargs)


def get_person_by_id_safe(user_id):
    return get_safely(client.person_by_id, user_id)


def get_fas_user_safe(username):
    return get_safely(client.person_by_username, username)


def get_bz_user_safe(bugzilla_email):
    return get_safely(bz.getuser, bugzilla_email)


def process_user(username):
    good_guy = False
    fas_user = get_fas_user_safe(username)
    if fas_user.status != u'active':
        return None
    try:
        human_name = get_bz_user_safe(fas_user.bugzilla_email).real_name
    except xmlrpc.client.Fault:
        return good_guy

    #bz.url_to_query("https://bugzilla.redhat.com/buglist.cgi?chfield=bug_status&chfieldfrom=2014-08-13&chfieldto=Now&classification=Fedora&component=Package%20Review&email1=msuchy%40redhat.com&emailassigned_to1=1&emailtype1=substring&list_id=3718380&product=Fedora&query_format=advanced")
    bugs = bz.query({'query_format': 'advanced',
        'component': 'Package Review', 'classification': 'Fedora', 'product': 'Fedora',
        'emailtype1': 'substring', 'email1': fas_user.bugzilla_email, 'emailassigned_to1': '1',
        'list_id': '3718380', 'chfieldto': 'Now', 'chfieldfrom': '-{0}d'.format(DAYS_AGO),
        'chfield': 'bug_status'})
    for bug in bugs:
        history = bug.get_history_raw()
        # 177841 is FE-NEEDSPONSOR
        if 177841 in bug.blocks:
            # check if sponsor changed status of the bug
            for change in history['bugs'][0]['history']:
                if change['when'] > datetime.date.today() - datetime.timedelta(DAYS_AGO):
                    if change['who'] == human_name:
                        for i in change['changes']:
                            if 'field_name' in i:
                                good_guy = True
                                print(u"{0} <{1}> worked on BZ {2}".format(human_name, username, bug.id))
                                break # no need to check rest of bug
                        else:
                            continue # hack to break to outer for-loop if we called break 2 lines above
                        break

        else:
            # check if sponsor removed FE-NEEDSPONSOR in past one year
            for change in history['bugs'][0]['history']:
                if change['when'] > datetime.date.today() - datetime.timedelta(DAYS_AGO):
                    if change['who'] == human_name:
                        for i in change['changes']:
                            if 'removed' in i and 'field_name' in i and \
			    i['removed'] == '177841' and i['field_name'] == 'blocks':
                                good_guy = True
                                print(u"{0} <{1}> removed FE-NEEDSPONSOR from BZ {2}".format(human_name, username, bug.id))
                                break # no need to check rest of bug
                        else:
                            continue # hack to break to outer for-loop if we called break 2 lines above
                        break

    if fas_user.id in DIRECTLY_SPONSORED:
        good_guy = True
        sponsored_users = DIRECTLY_SPONSORED[fas_user.id]
        sponsored_users = [convert_id_to_name(u) for u in sponsored_users]
        print(u"{0} <{1}> - directly sponsored: {2}".format(human_name, username, sponsored_users))

    if not good_guy:
        print(u"{0} <{1}> - no recent sponsor activity".format(human_name, username))

    return fas_user if good_guy else False

def config_value(raw_config, key):
    try:
        if six.PY3:
            return raw_config["main"].get(key, None)
        else:
            return raw_config.get("main", key, None)
    except configparser.Error as err:
        sys.stderr.write("Bad configuration file: {0}".format(err))
        sys.exit(1)

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
packager_group = client.group_by_name("packager")

DIRECTLY_SPONSORED = {}
for role in packager_group.approved_roles:
    if role.role_type == u'user':
        approved_date = datetime.datetime.strptime(role.approval, '%Y-%m-%d %H:%M:%S.%f+00:00')
        if approved_date > datetime.datetime.today() - datetime.timedelta(DAYS_AGO):
            if role.sponsor_id in DIRECTLY_SPONSORED:
                DIRECTLY_SPONSORED[role.sponsor_id].extend([role.person_id])
            else:
                DIRECTLY_SPONSORED[role.sponsor_id] = [role.person_id]

good_guys = []
for sponsor in sponsors:
    good_guys.append(process_user(sponsor))

good_guys_usernames = [sponsor.username for sponsor in good_guys if sponsor]
here = os.path.dirname(os.path.realpath(__file__))
dstdir = os.path.join(here, "_build")
if not os.path.exists(dstdir):
    os.makedirs(dstdir)
dst = os.path.join(dstdir, "active-sponsors.list")
with open(dst, "w") as f:
    f.write("\n".join(good_guys_usernames) + "\n")
