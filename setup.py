from pathlib import Path

from setuptools import setup


MODULE_NAME = "z_001_copago_services"
PACKAGE_ROOT = f"trytond.modules.{MODULE_NAME}"
REPORT_PACKAGE = f"{PACKAGE_ROOT}.report"
BASE_DIR = Path(__file__).parent


setup(
    name=MODULE_NAME,
    version="4.2.0",
    description="GNU Health copago v4 generation from appointments",
    long_description=(BASE_DIR / "README.rst").read_text(encoding="utf-8"),
    long_description_content_type="text/x-rst",
    author="ALFA Custom",
    packages=[
        PACKAGE_ROOT,
        REPORT_PACKAGE,
    ],
    package_dir={
        PACKAGE_ROOT: ".",
        REPORT_PACKAGE: "report",
    },
    package_data={
        PACKAGE_ROOT: [
            "tryton.cfg",
            "README.rst",
            "*.xml",
            "view/*.xml",
            "report/*.fodt",
            "report/*.odt",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "trytond>=6.0,<6.1",
        "gnuhealth==4.2.0",
    ],
    entry_points={
        "trytond.modules": [
            f"{MODULE_NAME} = {PACKAGE_ROOT}",
        ],
    },
)
