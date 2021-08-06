from datetime import datetime

from botto.models import Enablement
from botto.storage.storage import Storage


class EnablementStorage(Storage):
    def __init__(self, airtable_base: str, airtable_key: str):
        super().__init__(airtable_base, airtable_key)
        self.enablement_url = "https://api.airtable.com/v0/{base}/Enablement".format(
            base=airtable_base
        )

    async def add(self, name: str, enabled: str, enabled_by: str, message_link: str):
        enablement_data = {
            "Name": name,
            "Enabled": [enabled],
            "Enabled By": [enabled_by],
            "Date": datetime.utcnow().isoformat(),
            "Message Link": message_link
        }
        response = await self._insert(self.enablement_url, enablement_data)
        return Enablement.from_airtable(response)
