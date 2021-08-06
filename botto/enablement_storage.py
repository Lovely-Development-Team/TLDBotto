from datetime import datetime

import arrow

from botto.models import Enablement
from botto.storage.storage import Storage


class EnablementStorage(Storage):
    def __init__(self, airtable_base: str, airtable_key: str):
        super().__init__(airtable_base, airtable_key)
        self.enablement_url = "https://api.airtable.com/v0/{base}/Enablement".format(
            base=airtable_base
        )

    def add(self, name: str):
        enablement_data = {
            "Name": name,
            "Enabled": "",
            "Enabled By": "",
            "Date": datetime.utcnow(),
        }
        response = await self._insert(self.enablement_url, enablement_data)
        return Enablement.from_airtable(response)
