import os
import sys
import time
import shutil
import yaml
import html
import pytz
import munch
from datetime import datetime
from requests import ConnectionError
from jinja2 import Template
from fasjson_client import Client
from jinja2 import Environment, FileSystemLoader
from libravatar import libravatar_url


class Sponsor(munch.Munch):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._html_escape_strings()

    def _html_escape_strings(self):
        # puiterwijk, you prankster!
        for k, v in self.items():
            if type(v) == str:
                self[k] = html.escape(v)

    @property
    def timezone(self):
        return self.get("timezone") or "UTC"

    @property
    def human_name(self):
        return self.get("human_name") or self.get("username")

    @property
    def accounts_fpo_url(self):
        url = "https://accounts.fedoraproject.org/user/{0}"
        return url.format(self.username)

    @property
    def wiki_url(self):
        url = "https://fedoraproject.org/wiki/User:{0}"
        return url.format(self.username)

    @property
    def libravatar_img_url(self):
        return libravatar_url(email=self.emails[0], size=200, default="retro")

    @property
    def contact_url(self):
        # This shouldn't be link to the old FAS but at this momment,
        # accounts.fedoraproject.org doesn't show email addresses
        url =  "https://admin.fedoraproject.org/accounts/user/view/{0}"
        return url.format(self.username)

    @property
    def is_active(self):
        return getattr(self, "active", False)


def get_fas_client():
    return Client("https://fasjson.fedoraproject.org/")


def get_sponsors():
    client = get_fas_client()
    usernames = client.list_group_sponsors(groupname="packager").result
    return [Sponsor(client.get_user(username=sponsor["username"]).result)
            for sponsor in usernames]


def get_sponsors_mock():
    client = get_fas_client()
    usernames = ["frostyx", "msuchy", "praiskup", "schlupov"]
    return [Sponsor(client.get_user(username=x).result)
            for x in usernames]


def sponsor_by_username(username, sponsors):
    for sponsor in sponsors:
        if sponsor.username == username:
            return sponsor
    return None


def sponsors_by_areas_of_interest(sponsors):
    return sponsors_from_yaml("_build/interests.yaml", sponsors)


def sponsors_by_native_language(sponsors):
    return sponsors_from_yaml("_build/languages.yaml", sponsors)


def sponsors_from_yaml(path, sponsors):
    content = []

    try:
        with open(path, "r") as f:
            content = yaml.safe_load(f)
    except FileNotFoundError:
        print("Missing {0} file, you should probably run `make groups'"
              .format(path))

    result = {}
    for item in content:
        usernames = item.get("users", [])
        interested = [sponsor_by_username(u, sponsors) for u in usernames]
        interested = list(filter(None, interested))
        if not interested:
            continue
        title = item.get("title", item["id"].capitalize())
        result[title] = interested

    for _, group in result.items():
        set_sponsors_activity(group)
    return result


def sponsors_by_region(sponsors):
    # List of canonical timezones (well, their first parts) from
    # https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
    regions = {"Africa", "America", "Asia", "Atlantic", "Australia", "Europe",
               "Indian", "Pacific"}
    result = {}
    for sponsor in sponsors:
        if not sponsor.timezone:
            continue

        timezone = sponsor.timezone.split("/")[0]
        if not timezone in regions:
            continue

        result.setdefault(timezone, [])
        result[timezone].append(sponsor)
    return result


def sponsors_by_timezone(sponsors):
    result = {}

    # Let's use only numeric `seconds` values as keys so we can easily order the
    # dictinary once it is constructed
    for sponsor in sponsors:
        if not sponsor.timezone:
            continue

        # https://stackoverflow.com/a/5537943/3285282
        timezone = pytz.timezone(sponsor.timezone)
        timezone_now = datetime.now(timezone)
        seconds = timezone_now.utcoffset().total_seconds()

        result.setdefault(seconds, [])
        result[seconds].append(sponsor)

    # Transform the numeric keys to proper titles
    titled = {}
    for seconds, sponsors in sorted(result.items()):
        # First, let's figure out the title format
        if seconds > 0:
            title = "UTC +{}"
        elif seconds < 0:
            title = "UTC {}"
        else:
            title = "UTC"

        # If the offset is only hours, simply return its integer value
        # Otherwise calculate also the minutes offset
        hours = seconds/60/60
        if hours == int(hours):
            offset = int(hours)
        else:
            offset = time.strftime("%H:%M", time.gmtime(seconds)).lstrip("0")

        title = title.format(offset)
        titled[title] = sponsors

    return titled


def active_sponsors(sponsors):
    return [sponsor for sponsor in sponsors if sponsor.is_active]


def set_sponsors_activity(sponsors):
    here = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(here, "_build/active-sponsors.list")
    try:
        with open(path) as f:
            usernames = {x.strip() for x in f.readlines()}
    except FileNotFoundError:
        print("Cannot find {0} ... skipping".format(path))

    active = []
    for username in usernames:
        for i, sponsor in enumerate(sponsors):
            if username == sponsor.username:
                sponsor.update({"active": True})
                active.append(sponsors.pop(i))
                break

    for sponsor in reversed(active):
        sponsors.insert(0, sponsor)


def build_tag():
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


class Builder:
    def __init__(self, data):
        self.data = data

    @property
    def builddir(self):
        here = os.path.dirname(os.path.realpath(__file__))
        return os.path.join(here, "_build")

    def dump_html(self, name, content):
        raise NotImplemented

    @property
    def templates(self):
        return [
            "index.html.j2",
            "active.html.j2",
            "all.html.j2",
            "interests.html.j2",
            "languages.html.j2",
            "regions.html.j2",
            "timezones.html.j2",
        ]

    @property
    def options(self):
        return {}

    def build(self):
        for name in self.templates:
            builddir = self.builddir_rel_path(name)
            rendered = self.render_template(
                name,
                options=self.options,
                builddir_rel_path=builddir,
                **self.data
            )
            self.dump_html(name, rendered)

    def render_template(self, name, **kwargs):
        jinja_env = Environment(loader=FileSystemLoader("templates"))
        template = jinja_env.get_template(name)
        rendered = template.render(**kwargs)
        return rendered

    def write(self, path, content):
        dstdir = os.path.dirname(path)
        if not os.path.exists(dstdir):
            os.makedirs(dstdir)

        with open(path, "w") as child:
            child.write(content)

    def builddir_rel_path(self, template_name):
        """
        Path to the builddir but relative from the rendered template
        """
        # FIXME this is not really true, the relative path to builddir for HTML
        # (and/or base) builder is ./ but we need this path mainly only for
        # static files in HTML builder, so let's do such nasty workaround.
        return "../../"


class HtmlBuilder(Builder):
    @property
    def builddir(self):
        return os.path.join(super().builddir, "html")

    def dump_html(self, name, content):
        dstname = name.strip(".j2")
        dst = os.path.join(self.builddir, dstname)
        self.write(dst, content)


class DirHtmlBuilder(Builder):
    @property
    def builddir(self):
        return os.path.join(super().builddir, "dirhtml")

    @property
    def options(self):
        return {
            "dirhtml": True,
            "builddir": self.builddir,
        }

    def dump_html(self, name, content):
        dirname = name[:name.find(".")]
        dstdir = os.path.join(self.builddir, dirname)

        if dirname == "index":
            dstdir = self.builddir

        dst = os.path.join(dstdir, "index.html")
        self.write(dst, content)

    def build(self):
        super().build()
        here = os.path.dirname(os.path.realpath(__file__))
        filenames = ["style.css", "fedora-logo.png"]
        for filename in filenames:
            shutil.copy2(os.path.join(filename),
                        os.path.join(self.builddir, filename))

    def builddir_rel_path(self, template_name):
        """
        Path to the builddir but relative from the rendered template
        """
        if template_name == "index.html.j2":
            return "./"
        return "../"


class ProductionBuilder(DirHtmlBuilder):
    """
    This builder shouldn't be necessary and theoretically it should be possible
    to implement `DirHtmlBuilder` properly, to produce output, that can be
    viewed both locally and when deployed to the production instance.

    I am struggling to implement this and I don't want to waste any more time on
    this, so I am creating a builder specially for the output that is going to
    be deployed to production.

    Don't bother review it locally, it will look broken.
    """

    @property
    def builddir(self):
        base_builddir = super(DirHtmlBuilder, self).builddir
        return os.path.join(base_builddir, "production")

    def builddir_rel_path(self, template_name):
        return "./"


def main():
    try:
        sponsors = get_sponsors_mock()
        # sponsors = get_sponsors()
    except ConnectionError:
        print("Unable to get sponsors, try again.")
        sys.exit(1)

    set_sponsors_activity(sponsors)
    data = {
        "sponsors": sponsors,
        "active": active_sponsors(sponsors),
        "interests": sponsors_by_areas_of_interest(sponsors),
        "regions": sponsors_by_region(sponsors),
        "timezones": sponsors_by_timezone(sponsors),
        "languages": sponsors_by_native_language(sponsors),
        "build_tag": build_tag(),
    }

    for builder_class in [HtmlBuilder, DirHtmlBuilder, ProductionBuilder]:
        builder = builder_class(data)
        builder.build()


if __name__ == "__main__":
    main()
