# Portolan Conformance

Conformance means passing [rashid](https://github.com/portolan-sdi/rashid),
not claiming to conform, so it runs in CI:

```bash
python3 tests/test_conformance.py
```

That gate fails on any error-severity finding whose rule is not listed below.
The list starts empty and it must never grow without a row here. A known
deviation with an issue number is a debt someone can pay off. A silently
widened allow-list is a false claim about what this catalog conforms to.

## The rashid version floor

The gate needs rashid `>=0.1.8,<0.2.0`. It reads `rashid --version` and fails
outside that range. It also fails when rashid is absent, and prints the install
command. A skip would report a green run for a catalog that no validator read.

The floor is 0.1.8 because it is the first rashid that accepts the v0.2.0 root
`self` link this catalog carries (PORTO-CORE-081). Rules PTL-LNK-007,
PTL-LNK-008, PTL-LNK-009 and PTL-AST-006 do not exist below 0.1.5. The gate asserts all four. An older rashid
reports a pass for a catalog that it never checked against them. The same range
is in `portolan-cli/pyproject.toml` and in the CI install step.

The upper bound stops an unreviewed 0.2 rule set from changing what this gate
means. Raise both bounds together when you move to 0.2, and read the new rules
first.

This file also records workarounds for the other validator CI runs. Those are
not conformance debts, because the catalog is correct and the validator is not.
They live here so nobody has to read CI code to find out why a gate skips
something.

## Accepted deviations

`ACCEPTED` is empty. One finding pair is exempted by shape instead, because the
catalog is correct where it is published and only the checkout is partial.

| Rule | Where | Why accepted | Tracking |
|---|---|---|---|
| PTL-LNK-006 | `child` links from the three `oam-*/collection.json` to `./<year>/catalog.json` | The year tree is generated to the bucket, not committed | By design, see below |
| PTL-COL-005 | the three `oam-*/collection.json` | Their items are in the uncommitted year tree | By design, see below |

### The generated year tree

The catalog has 21,863 items in 46 year subcatalogs. Committing them would put
about 22,000 files in git and rewrite most of them on each re-harvest, so they
are generated instead, as the
[git-backed catalogs guide](https://github.com/portolan-sdi/portolan-spec/blob/main/specs/best-practices/git-backed-catalogs.md)
recommends for large item collections. `python -m oam_mirror.build` writes the
full catalog to `build/site/`, and `tools/upload_generated.py` uploads the part
git does not track. Fields of the World publishes its Sentinel-2 item tree the
same way, with the same two scoped exemptions.

A checkout therefore shows each collection with relative `child` links to year
catalogs that are absent, and with an item mirror (`items.parquet`, referenced
by its published URL) but no items. Both hold in the published catalog. The
full catalog is checked before every upload with
`portolan check --data-scope local` in `build/site/`.

`tests/test_links.py` and `tests/test_conformance.py` match these findings by
file and target, not by rule id, so the same rules still fail on any other
document or link.

<!--
When you accept one, add a row and a section explaining it, like this:

| Rule | Where | Why accepted | Tracking |
|---|---|---|---|
| PTL-VIZ-001 | all thumbnails | WebP is not yet permitted; the size saving is 4x | portolan-spec#121 |

Then add the rule id to ACCEPTED in tests/test_conformance.py. Both, or
neither.
-->

## Validator workarounds

### stac-check reports a dialect crash on every collection

`tests/test_stac_valid.py` exempts one stac-check failure:

```
'list' object has no attribute 'get'
[Schema: https://schemas.portolan-sdi.org/portolan/vX.Y.Z/schema.json]. Error in Extensions.
```

The Portolan schema is valid draft-07, and rashid validates catalogs against it
cleanly. `stac-validator`, which stac-check uses, hardcodes the JSON Schema
2020-12 dialect and ignores the `$schema` a schema declares. The profile schema
uses the draft-07 tuple form of `items` in `valid_bbox`, which means something
different under 2020-12, so the library raises instead of validating.

Tracked upstream at <https://github.com/stac-utils/stac-check/issues/159>,
and on the Portolan side at
<https://github.com/portolan-sdi/portolan-spec/issues/157>.

The exemption matches that exact message, and only when the failing schema is a
Portolan profile schema. Every other stac-check error still fails the build,
and the gate prints how many objects took the exemption.

The exemption expires on its own. The gate fails once stac-check stops emitting
the crash on a collection or item that declares the profile schema, and tells
you to delete both the exemption and this section. CI installs stac-check
unpinned, so the next release triggers that without anyone watching for it.

`tests/test_stac_valid.py` also fails when stac-check is absent, and prints the
install command. It takes no version floor and no pin. The rashid floor exists
because that gate asserts four named rules. This gate asserts no stac-check
rule. It needs the opposite property. A pin holds the exemption open after the
upstream fix ships.
