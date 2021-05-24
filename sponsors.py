import pytz
import html
from datetime import datetime
from jinja2 import Template
from fasjson_client import Client
from jinja2 import Environment, FileSystemLoader


def get_fas_client():
    return Client("https://fasjson.fedoraproject.org/")


def get_sponsors():
    client = get_fas_client()
    usernames = client.list_group_sponsors(groupname="packager").result
    sponsors = [client.get_user(username=sponsor["username"]).result
                for sponsor in usernames]

    # Set some reasonable defaults
    for sponsor in sponsors:
        sponsor["timezone"] = sponsor["timezone"] or "UTC"
        sponsor["human_name"] = sponsor["human_name"] or sponsor["username"]

    # puiterwijk, you prankster!
    for sponsor in sponsors:
        for k, v in sponsor.items():
            if type(v) == str:
                sponsor[k] = html.escape(v)
    return sponsors


def get_sponsors_mock():
    client = get_fas_client()
    usernames = ["frostyx", "msuchy", "praiskup", "schlupov"]
    return [client.get_user(username=x).result for x in usernames]


def render_html(**kwargs):
    jinja_env = Environment(loader=FileSystemLoader("."))
    template = jinja_env.get_template("sponsors.html.j2")
    rendered = template.render(**kwargs)
    with open("sponsors.html", "w") as child:
        child.write(rendered)


def sponsors_by_areas_of_interest(sponsors):
    # TODO Parse these from some yaml
    return {
        "C/C++": [sponsors[0]],
        "Python": [sponsors[0], sponsors[1]],
        "Ruby": [sponsors[2]],
    }


def sponsors_by_native_language(sponsors):
    # TODO Parse these from some yaml
    return {
        "Czech": [sponsors[0]],
        "French": [sponsors[0], sponsors[1]],
        "German": [sponsors[2]],
    }


def sponsors_by_region(sponsors):
    # List of canonical timezones (well, their first parts) from
    # https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    regions = {"Africa", "America", "Asia", "Atlantic", "Australia", "Europe",
               "Indian", "Pacific"}
    result = {}
    for sponsor in sponsors:
        if not sponsor["timezone"]:
            continue

        timezone = sponsor["timezone"].split("/")[0]
        if not timezone in regions:
            continue

        result.setdefault(timezone, [])
        result[timezone].append(sponsor)
    return result


def sponsors_by_timezone(sponsors):
    now = datetime.now()
    utc = pytz.timezone("UTC")
    result = {}
    for sponsor in sponsors:
        if not sponsor["timezone"]:
            continue

        timezone = pytz.timezone(sponsor["timezone"])
        delta = utc.localize(now) - timezone.localize(now)
        hours = int(delta.seconds / 3600)

        if hours > 0:
            title = "UTC +{}"
        elif hours < 0:
            title = "UTC {}"
        else:
            title = "UTC"

        title = title.format(hours)
        result.setdefault(title, [])
        result[title].append(sponsor)
    return result


def main():
    # sponsors = get_sponsors_mock()
    sponsors = get_sponsors()
    interests = sponsors_by_areas_of_interest(sponsors)
    regions = sponsors_by_region(sponsors)
    timezones = sponsors_by_timezone(sponsors)
    languages = sponsors_by_native_language(sponsors)
    render_html(
        sponsors=sponsors,
        interests=interests,
        regions=regions,
        timezones=timezones,
        languages=languages,
    )


if __name__ == "__main__":
    main()
