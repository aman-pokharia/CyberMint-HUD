import unittest
from dataclasses import dataclass

from cybermint_hud.applications import enumerate_applications, filter_applications, launch_application


@dataclass
class FakeApp:
    name: str
    keywords: tuple[str, ...] = ()
    visible: bool = True
    launch_error: Exception | None = None

    def should_show(self):
        return self.visible

    def get_name(self):
        return self.name

    def get_keywords(self):
        return self.keywords

    def launch(self, files, context):
        if self.launch_error:
            raise self.launch_error
        return True


class FakeAppInfoApi:
    apps = []

    @classmethod
    def get_all(cls):
        return cls.apps


class ApplicationsTests(unittest.TestCase):
    def test_discovery_skips_hidden_apps_and_sorts_names(self):
        FakeAppInfoApi.apps = [FakeApp("Terminal"), FakeApp("Hidden", visible=False), FakeApp("Browser")]
        result = enumerate_applications(FakeAppInfoApi)
        self.assertEqual([app.name for app in result], ["Browser", "Terminal"])

    def test_search_matches_names_and_keywords_case_insensitively(self):
        FakeAppInfoApi.apps = [FakeApp("Web Browser", ("internet", "network")), FakeApp("Text Editor", ("writing",))]
        apps = enumerate_applications(FakeAppInfoApi)
        self.assertEqual([app.name for app in filter_applications(apps, "NET web")], ["Web Browser"])
        self.assertEqual([app.name for app in filter_applications(apps, "writing")], ["Text Editor"])

    def test_launch_success_and_failure_are_reported(self):
        good = enumerate_applications(type("Api", (), {"get_all": staticmethod(lambda: [FakeApp("Editor")])})) [0]
        failed_entry = enumerate_applications(type("Api", (), {"get_all": staticmethod(lambda: [FakeApp("Broken", launch_error=RuntimeError("desktop file missing"))])})) [0]
        self.assertEqual(launch_application(good), (True, ""))
        self.assertEqual(launch_application(failed_entry), (False, "desktop file missing"))


if __name__ == "__main__":
    unittest.main()
