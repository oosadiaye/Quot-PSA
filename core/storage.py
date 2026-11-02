"""File storage for files that must never be reachable by a URL."""
from django.core.files.storage import FileSystemStorage


class PrivateFileSystemStorage(FileSystemStorage):
    """A filesystem storage that refuses to produce a URL.

    Plain ``FileSystemStorage`` falls back to ``MEDIA_URL`` and will happily
    build a ``/media/...`` address for any file. For a private file that is a
    trap: someone later renders ``file.url`` into a page, or a web-server rule
    starts serving the folder. Refusing here keeps the only read path the
    authenticated endpoint that checks who is asking.
    """

    def url(self, name):
        raise ValueError(
            'Private files have no URL; read them through the authenticated download endpoint.'
        )
