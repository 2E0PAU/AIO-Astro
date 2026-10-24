# Third-party notices

AIO Astro source is GPL-3.0-or-later. Runtime dependencies and their transitive
dependencies retain their own licenses. Installing dependencies does not replace
their upstream terms; their installed distribution metadata includes license files.

Primary projects:

- [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/licenses.html): this
  project uses the Essentials package. Consult Qt's module-specific license files
  when preparing application bundles and include the required notices and materials.
- [qasync](https://github.com/CabbageDevelopment/qasync)
- [Astropy](https://www.astropy.org/)
- [NumPy](https://numpy.org/)
- [SciPy](https://scipy.org/): BSD-3-Clause; binary wheels also include their
  platform-specific dependency notices in installed metadata.
- [HTTPX](https://www.python-httpx.org/)
- [Astropy IERS data](https://github.com/astropy/astropy-iers-data)

The bundled catalog adapts [HYG v4.1](https://github.com/astronexus/HYG-Database/tree/main/hyg)
and [OpenNGC](https://github.com/mattiaverga/OpenNGC), under CC BY-SA 4.0. The
adapted data remains CC BY-SA 4.0. Milky Way and constellation layers are from
[d3-celestial](https://github.com/ofrohn/d3-celestial), retaining Olaf Frohn's
BSD-3-Clause notice and José R. Vieira's Milky Way outline credit. No photographic
sky survey is redistributed. Full source versions, checksums, modifications,
acknowledgements and license texts are in [the data directory](src/aio_astro/data/README.md)
and are packaged alongside the assets in the wheel.

ASCOM Alpaca and PHD2 are independent projects. Their published protocols are used
for interoperability; their software is not bundled here. N.I.N.A. and Cartes du
Ciel are workflow references. No source from those applications is included.

ASTAP binaries, reference databases and source are downloaded separately as inputs
for a future macOS distribution, outside the current application wheel. See the
[asset inventory and packaging notes](vendor/astap/README.md). ASTAP is by Han Kleijn
under MPL-2.0; its upstream notices and full license are preserved there. D80/G05
star data retain their Gaia/ESA/DPAC credits. The original database package also
contains unrelated catalogs with separate terms; the future runtime payload must
select only the required star tiles. W08 provenance remains to be resolved before
public redistribution. These materials do not acquire Peter Dossett's project
copyright or the application's GPL license.

The local saved-FITS workflow uses separately prepared ASTAP CLI and D80/G05
tiles. The downloaded AAO/ROE DSS image used in opt-in solving trials remains a
local validation fixture, outside the wheel/source distribution; its provenance
is recorded in [the solving guide](docs/PLATE_SOLVING.md).

ZWO's **ASI Camera SDK 1.41** is downloaded separately for direct USB camera
support. Its MIT-style copyright/permission notice and unmodified ABI header are
retained under [vendor/zwo](vendor/zwo/README.md). The prepared Mac runtime links
dynamically to **libusb 1.0.30**, licensed LGPL-2.1-or-later. Its full source archive,
licence and reproducible preparation instructions are retained there for future
distribution. Prepared SDK copies have relocated Mach-O dependency paths and
local ad-hoc signatures; fetched originals remain unchanged. These native assets
are outside the Python wheel. A future app distribution must include applicable
notices, corresponding libusb source and replaceable shared-library support.

ZWO's **EAF SDK 1.8.1** is downloaded separately for USB focus control, including
the original EAF. The full 2015 ZWO Company MIT-style permission notice and
unmodified ABI header are retained in [vendor/eaf](vendor/eaf/README.md). Runtime
dylib copies have local ad-hoc signatures and use system frameworks. Original
archives remain unchanged; native files are outside the Python wheel. Include
the upstream copyright/permission notice when distributing native copies.
