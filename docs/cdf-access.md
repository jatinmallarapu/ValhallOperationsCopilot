# Acquiring and replaying CDF data

As checked in November 2026, Cognite's [Open Industrial Data course](https://learn.cognite.com/open-industrial-data)
still describes free access. The [official dataset repository](https://github.com/cognitedata/open-industrial-data)
describes the Valhall first-stage compressor dataset. Availability of course material
does not verify access to a particular tenant or successful credentials.

1. Register through [Cognite Hub](https://hub.cognite.com/), follow its current Open
   Industrial Data access instructions, and complete the introductory Academy
   courses yourself. Check the tenant, base URL, project and permitted auth flow.
2. Install Python 3.12 and `pip install -e '.[cdf]'`. Copy `.env.example` to `.env`,
   fill the four COGNITE values locally, and load them into your shell environment.
   Python does **not** auto-load `.env`. Never paste a secret into a GitHub issue.
3. Verify credentials and discover a root asset with the SDK:

```python
from app.cdf_client import sdk_client

client = sdk_client()
print([(a.id, a.name) for a in client.assets.list(limit=5)])
print([(s.id, s.name) for s in client.time_series.list(limit=5)])
```

The wrapper uses OAuth client credentials against the tenant you configure.
Personal interactive access may require a different credential provider; adapt
`sdk_client` to the authentication flow issued to your account. No secret or real
asset ID is distributed in this repository.

Acquire a bounded subtree and explicit UTC date window, substituting your asset ID:

```sh
python -m app.cdf_client --root-id 123456 --start 2024-01-01 --end 2024-01-08
COPILOT_DATA=data/cache/snapshot.json uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`123456` is a placeholder, not a claimed Valhall asset. In PowerShell set
`$env:COPILOT_DATA='data/cache/snapshot.json'` before starting Uvicorn.
Restart after changing the manifest. This offline replay requires no credentials.
The importer writes timestamped Parquet tables and atomically replaces the JSON
manifest. Limits of 1,000 assets/series and 10,000 points per series fail closed
instead of silently truncating a larger request. The importer retrieves hourly
averages; the API calculates min/max of those averages, not extrema of raw signals.

For Docker, mount the snapshot read-only and set `COPILOT_DATA` in a local Compose
override. The default Compose file deliberately loads the bundled synthetic data.
Data ownership and redistribution terms remain those of the original providers.
Keep acquired data under ignored `data/cache/`; do not publish it automatically.

## Verification status

The CDF adapter is verified with a mocked SDK client. An authenticated CDF read has
**not** been performed in this build. The bundled corpus is generated, not downloaded
from Cognite or Aker BP. Replace this status only after a successful acquisition,
and record date, scope, aggregate, missing-data rate and applicable usage terms.
