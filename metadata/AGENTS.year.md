# $title: agent guide

This subcatalog groups $count items of the `$collection_id` collection by acquisition start year. It exists only to make browsing easier. Do not crawl it item by item. Query `../items.parquet` instead, as the collection [AGENTS.md](../AGENTS.md) shows, filtering on `year(coalesce(datetime, start_datetime))`$year_filter.
