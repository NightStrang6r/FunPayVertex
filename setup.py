from pip._internal.cli.main import main


common_packages = [
    "psutil>=5.9.4",
    "beautifulsoup4>=4.11.1",
    "colorama>=0.4.6",
    "requests==2.28.1",
    "pytelegrambotapi==4.8.0",
    "pillow>=9.3.0",
    "aiohttp>=3.9.5",
    "requests_toolbelt==0.10.1",
    "PySocks>=1.7.1"
]


def install_packages(packages_list: list[str]):
    failed_packages = []
    for pkg in packages_list:
        if main(["install", "-U", pkg]):
            failed_packages.append(pkg)
    if failed_packages:
        raise SystemExit(f"Failed to install packages: {', '.join(failed_packages)}")


if __name__ == '__main__':
    install_packages(common_packages)
