""""
Copyright © Krypton 2019-2023 - https://github.com/kkrypt0nn (https://krypton.ninja)

Version: 6.1.0

Modified by z4kky - https://github.com/z4kkyy
"""


import aiosqlite


class DatabaseManager:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection
