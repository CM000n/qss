<div align="center">
  <a href="https://questdb.io/" target="blank"><img alt="QuestDB Logo" src="https://questdb.io/img/questdb-logo-themed.svg" width="305px"/></a>
</div>

QuestDB state storage (QSS) custom component for Home Assistant
========================================

QSS makes it possible to transfer state information of the Home Assistant entities simply and efficiently via InfluxDB Line Protocol into a QuestDB for long-term storage and later analysis.

What ist [QuestDB](https://questdb.io/)?
[QuestDB](https://questdb.io/) is the new kid on the block of time series optimised databases and claims to be the fastest open source time series database currently available.
QuestDB offers high throughput ingestion and real-time SQL queries for applications in a wide range of use cases. It has a tiny memory footprint and combines the best of different worlds by supporting record entry via the fast and simple InfluxDB Line protocol, while offering great compatibility for common SQL queries (PostgresSQL).
If you want to learn more about the possibilities of QuestDB, have a look at the [documentation](https://questdb.io/docs/) or this great [Youtube video by Code to the Moon](https://www.youtube.com/watch?v=A8uMF64rbS8).

QSS itself is not a replacement for the recorder component integrated in Home Assistant, but merely offers an alternative for long-term data storage.

## Installation

### Precondition
* Make sure that your QuestDB instance is up and running.
* Possible installation methods for QuestDB can be found in the ['Get started' section of the documentation](https://questdb.io/docs/#get-started).
* Apart from that, you do not need to take any further precautions at present. QSS automatically creates a table named ```qss``` in which it stores the data.


### Installation of the QSS component:
Manual:
* Copy the ```qss``` folder in the ```custom_components``` folder of this repository into the ```custom_components``` folder of your Home Assistant installation.

Automatic:
* Add this repository as a custom repository to your [HACS](https://hacs.xyz/) installation. You can then install QSS via HACS. Full HACS compatibility and inclusion in the official HACS repo collection is planned for the future.


configuration.yaml
* Add an entry to your Home Assistant ```configuration.yaml``` that might look like this::

```yaml
qss:
  host: "192.168.178.3"
  port: 9009
  include:
    domains:
      - "sensor"
    entities:
      - "person.john_doe"
```

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
The data is stored in a QuestDB table named ``qss``, which has the following structure:

| Column name: | entity_id | state  | attributes | timestamps |
|:-------------|:---------:|:------:|:----------:|:----------:|
| Type:        | symbol    | string | string     | timestamps |

## Credits
QSS was largely inspired by and based on [LTSS (Long Time State Storage)](https://github.com/freol35241/ltss) by [freol35241](https://github.com/freol35241). Many thanks to [freol35241](https://github.com/freol35241) for his great work!

## Disclaimer
* QSS is not an official extension of the QuestDB project and is not directly related to it.
* No liability is accepted for any loss of data that may occur through the use of QSS. Use at your own risk!
