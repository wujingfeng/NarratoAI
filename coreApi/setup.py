"""Selective wheel build for the legacy worker modules Core actually uses."""

from setuptools import setup
from setuptools.command.build_py import build_py


class SelectiveLegacyBuildPy(build_py):
    """Exclude unrelated legacy modules from the Core wheel."""

    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        if package == "app.services":
            allowed = {"__init__", "fun_asr_subtitle", "media_probe"}
            return [item for item in modules if item[1] in allowed]
        return modules


setup(cmdclass={"build_py": SelectiveLegacyBuildPy})
