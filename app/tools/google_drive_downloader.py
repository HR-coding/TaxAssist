from tools.google_drive_client import (
    get_drive_service
)

from googleapiclient.http import (
    MediaIoBaseDownload
)

import io
import os


def download_file(
    file_id,
    file_name
):

    service = get_drive_service()

    os.makedirs(
        "temp",
        exist_ok=True
    )

    request = (
        service.files()
        .get_media(
            fileId=file_id
        )
    )

    path = os.path.join(
        "temp",
        file_name
    )

    fh = io.FileIO(
        path,
        "wb"
    )

    downloader = (
        MediaIoBaseDownload(
            fh,
            request
        )
    )

    done = False

    while not done:

        status, done = (
            downloader.next_chunk()
        )

    return path