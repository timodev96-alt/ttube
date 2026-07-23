from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='ttube',
    version='0.1.0',
    description='Youtube Video/Audio Downloader!',
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=['yt_dlp','imageio-ffmpeg'],
    author='Timothy Emad',
    entry_points={
        'console_scripts':[
            'ttube=ttube.cli:main',
        ],
    },
)