import os
import yaml
import requests
from fasjson_client import Client


def get_sponsors_usernames():
    client = Client("https://fasjson.fedoraproject.org/")
    return [sponsor["username"] for sponsor in
            client.list_group_sponsors(groupname="packager").result]


def get_sponsors_usernames_mock():
    return ["frostyx", "msuchy", "praiskup", "schlupov"]


def fetch_personal_config(username):
    url = "https://{0}.fedorapeople.org/sponsor.yaml".format(username)
    response = requests.get(url)
    if response.status_code != 200:
        return None
    return yaml.safe_load(response.text)


def fetch_personal_configs():
    usernames = ["frostyx"]
    return [fetch_personal_config(username) for username in usernames]


def load_upstream_config(path):
    with open(path, "r") as f:
        content = yaml.safe_load(f)
    return content


def update_upstream_config(config, group_ids, username):
    for group in config:
        if group["id"] in group_ids:
            group.setdefault("users", [])
            group["users"].append(username)


def dump_build_file(filename, content):
    here = os.path.dirname(os.path.realpath(__file__))
    dstdir = os.path.join(here, "_build")
    if not os.path.exists(dstdir):
        os.makedirs(dstdir)
    dst = os.path.join(dstdir, filename)
    with open(dst, "w") as f:
        f.write(content)


def main():
    interests = load_upstream_config("interests.yaml")
    languages = load_upstream_config("languages.yaml")
    configs = fetch_personal_configs()

    # usernames = get_sponsors_usernames_mock()
    usernames = get_sponsors_usernames()
    for username in usernames:
        config = fetch_personal_config(username)
        if not config:
            continue

        print("Found config for {0}".format(username))
        update_upstream_config(interests, config.get("interests", []), username)
        update_upstream_config(languages, config.get("languages", []), username)

    dump_build_file("interests.yaml", yaml.dump(interests))
    dump_build_file("languages.yaml", yaml.dump(languages))


if __name__ == "__main__":
    main()
