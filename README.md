<div align="center">
  <a href="https://questdb.io/" target="blank"><img alt="QuestDB Logo" src="https://questdb.io/img/questdb-logo-themed.svg" width="305px"/></a>

  <h1>QuestDB State Storage (QSS)</h1>
  <p><strong>Store your Home Assistant entity states in QuestDB — fast, async and HACS-ready.</strong></p>

  [![GitHub release](https://img.shields.io/github/v/release/CM000n/qss?style=for-the-badge&logo=homeassistantcommunitystore&color=blue)](https://github.com/CM000n/qss/releases)
  [![HACS default](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge&logo=homeassistant)](https://github.com/hacs/default)
  [![Validate](https://img.shields.io/github/actions/workflow/status/CM000n/qss/validate.yml?branch=main&style=for-the-badge&label=Validate)](https://github.com/CM000n/qss/actions/workflows/validate.yml)
  [![Tests](https://img.shields.io/github/actions/workflow/status/CM000n/qss/tests.yml?branch=main&style=for-the-badge&label=Tests)](https://github.com/CM000n/qss/actions/workflows/tests.yml)
  [![License](https://img.shields.io/github/license/CM000n/qss?style=for-the-badge)](LICENSE)

  [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=CM000n&repository=qss&category=integration)
</div>

QSS makes it possible to transfer state information of the Home Assistant entities simply and efficiently via InfluxDB Line Protocol into a QuestDB for long-term storage and later analysis.

**What is [QuestDB](https://questdb.io/)?**
[QuestDB](https://questdb.io/) is the new kid on the block of time series optimised databases and claims to be the fastest open source time series database currently available.
QuestDB offers high throughput ingestion and real-time SQL queries for applications in a wide range of use cases. It has a tiny memory footprint and combines the best of different worlds by supporting record entry via the fast and simple InfluxDB Line protocol, while offering great compatibility for common SQL queries (PostgresSQL).
If you want to learn more about the possibilities of QuestDB, have a look at the [documentation](https://questdb.io/docs/) or this great [Youtube video by Code to the Moon](https://www.youtube.com/watch?v=A8uMF64rbS8).

QSS itself is not a replacement for the recorder component integrated in Home Assistant, but merely offers an alternative for long-term data storage.

## Features

- ⚡ **Persistent, batched writes** — a single, reused QuestDB connection is shared across events; rows are buffered and flushed once `max_batch_size` is reached or `flush_interval_seconds` has elapsed, whichever comes first.
- 🔁 **Automatic retries** on transient ingestion errors, so a brief network hiccup doesn't drop your data.
- 🎯 **Fine-grained filtering** — include or exclude specific domains, entities, or entity glob patterns (e.g. `sensor.weather_*`) from being recorded.
- 🔒 **Optional authenticated & SSL/TLS connections**, for secured QuestDB / QuestDB Enterprise setups.
- 🗄️ **Configurable target table**, so multiple Home Assistant instances can share the same QuestDB without colliding.
- ✅ **Well tested** with [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component), covering filtering, ingestion/retry behavior and the setup/shutdown lifecycle.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Details](#details)
- [Development](#development)
- [Credits](#credits)
- [Disclaimer](#disclaimer)

## Installation

### Precondition

- Make sure that your QuestDB instance is up and running.
- Possible installation methods for QuestDB can be found in the ['Get started' section of the documentation](https://questdb.io/docs/#get-started).
- Apart from that, you do not need to take any further precautions at present. QSS automatically creates a table named `qss` in which it stores the data.

### Installation of the QSS component:

Manual:

- Copy the `qss` folder in the `custom_components` folder of this repository into the `custom_components` folder of your Home Assistant installation.

Automatic (via [HACS](https://hacs.xyz/)):

- QSS is part of the official HACS default repository collection, so it can be installed directly without adding a custom repository first: open HACS, search for "QuestDB State Storage (QSS)" and install it from there.
- Alternatively, you can still add this repository as a custom repository to your HACS installation if you want to track a specific branch or fork.

configuration.yaml

- Add an entry to your Home Assistant `configuration.yaml` that might look like this::

```yaml
qss:
  host: "192.168.178.3"
  port: 9009
  authentication:
    ssl_check: True
    kid: "your_kid"
    d_key: "your_d_key"
    x_key: "your_x_key"
    y_key: "your_y_key"
  include:
    domains:
      - "sensor"
    entities:
      - "person.john_doe"
```

Note: Authenication details are completely optional. How to create them can be found in the Quest DB documentation at this point:
https://questdb.io/docs/reference/api/ilp/authenticate

## Configuration

```yaml
qss:
(map)(Required)
Enables the qss integration. Only allowed once.

  host:
  (string)(Required)
  The URL or IP Address that points to your QuestDB database.

  port:
  (int)(Required)
  The port to the InfluxDB line protocol of your QuestDB installation. This is normally 9009 by default.

  table_name:
  (string)(Optional)
  The name of the QuestDB table QSS should store the state data in. Defaults to `qss`. Useful if you want to keep multiple Home Assistant instances or environments separated within the same QuestDB.

  max_batch_size:
  (int)(Optional)
  QSS keeps a single, persistent connection to QuestDB open and reuses it for many events instead of opening a new connection per event. Rows are buffered and only sent to QuestDB once this many rows have accumulated (or once `flush_interval_seconds` has elapsed, whichever happens first). Defaults to `500`.

  flush_interval_seconds:
  (int)(Optional)
  The maximum number of seconds buffered rows may stay unflushed before being sent to QuestDB, even if `max_batch_size` has not yet been reached. Defaults to `5`.

  authentication:
  (dict)(Optional)
  Under this entry you can, if desired, enter the authenication parameters necessary for your Quest DB installation. The entry is completely optional if your Quest DB installation does not have any additional authentication settings. Keep in mind that this authentication needs an SSL setup, either from QuestDB Enterprise or a reverse proxy.

    ssl_check:
    (bool)(Optional)
    If you want to surpress the check of the SSL certificate of your QuestDB installation, set this to `False`. Default to `True`

    kid:
    (string)(Required)
    Your authentication kid.

    d_key: "your_d_key"
    (string)(Required)
    Your authentication D Key.

    x_key: "your_x_key"
    (string)(Required)
    Your authentication X Key.

    y_key: "your_y_key"
    (string)(Required)
    Your authentication Y Key.

  exclude:
  (map)(Optional)
  Configure which integrations should be excluded from recordings.

    domains:
    (List[str])(Optional)
    The list of domains to be excluded from recordings.

    entities:
    (List[str])(Optional)
    The list of entity ids to be excluded from recordings.

    entity_globs:
    (List[str])(Optional)
    Exclude all entities matching a listed pattern from recordings (e.g., `sensor.weather_*`).

  include:
  (map)(Optional)
  Configure which integrations should be included in recordings. If set, all other entities will not be recorded.

    domains:
    (List[str])(Optional)
    The list of domains to be included in the recordings.

    entities:
    (List[str])(Optional)
    The list of entity ids to be included in the recordings.

    entity_globs:
    (List[str])(Optional)
    Include all entities matching a listed pattern from recordings (e.g., `sensor.weather_*`).
```

## Details

The data is stored in a QuestDB table named `qss` by default (configurable via `table_name`), which has the following structure:

| Column name: | entity_id | state  | attributes | timestamps |
| :----------- | :-------: | :----: | :--------: | :--------: |
| Type:        |  symbol   | string |   string   | timestamps |

## Development

QSS uses [Poetry](https://python-poetry.org/) for dependency management and [pytest](https://pytest.org/) (via [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)) for testing. It requires Python 3.14+, matching the Python version required by current Home Assistant releases.

```bash
# Install dependencies (including dev/test dependencies)
poetry install

# Run the test suite with coverage
poetry run pytest tests/

# Run linting/formatting
poetry run pre-commit run --all-files
```

The test suite covers the entity filtering logic, the QuestDB ingestion/retry behavior, and the integration setup/shutdown lifecycle without requiring a running QuestDB instance or Home Assistant installation.

## Credits

- First of all, thanks to all the contributors to the great [QuestDB project](https://github.com/questdb/questdb). Without their work, this custom component would never have been created.
- QSS was largely inspired by and based on [LTSS (Long Time State Storage)](https://github.com/freol35241/ltss) by [freol35241](https://github.com/freol35241). Many thanks to [freol35241](https://github.com/freol35241) for his great work!

## Disclaimer

- QSS is not an official extension of the [QuestDB project](https://github.com/questdb/questdb) and is not directly related to it.
- No liability is accepted for any loss of data that may occur through the use of QSS. Use at your own risk!
