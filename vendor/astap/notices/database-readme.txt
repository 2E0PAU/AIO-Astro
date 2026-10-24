Compact star databases for the ASTAP program:

Star databases usability:

D80 star database for 6°>FOV>0.15°
D50 star database for 6°>FOV>0.2°
D20 star database for 6°>FOV>0.3°
D05 star database for 6°>FOV>0.6°
V50 as D50 but for photometry.
G05 star database for 20°>FOV>3°
W08 star database for 80°>FOV>20°


ASTAP for Windows users:
Download and install the D80 or D50 database installer (d80_star_database.exe or d50_star_database.exe ). If you want to save disk space the D20 or D05 instead depending on your setup field-of-view. You will need only one database. Alternatively you can continue using the older H18 or H17 database.


ASTAP for Linux users:
Download and install the D80 or D50 database package (d80_star_database.deb or d50_star_database.deb). If you want to save disk space the D20 or D05 instead depending on your setup field-of-view. You will need only one database.  The files will be placed in the ASTAP program directory /opt/astap.


ASTAP for macOS users:
Download and install the D80 or D50 database pkg file (d80_star_database.pkg or d50_star_database.pkg).  If you want to save disk space the D20 or D05 instead depending on your setup field-of-view. You will need only one database.  The files will be placed in directory /usr/local/opt/astap.

For the rare case you have more then one database installed and the selection is set on auto then the database selection will be as follows:

FOV>20° ==> if exist W08
ELSE
FOV>6° ==> if exist G05
ELSE
FOV<0.5° ==> if exist D80
ELSE
==> if exist V50, D50, D20, D20, G05


The database is sorted on star density. D80 indicates 8000 stars per square degree. D50 indicates 5000 stars per square degree. D20 indicates 2000 stars per square degree. D05 indicates 500 stars per square degree. Epoch is fixed at year 2025. The magnitude is the Gaia Bp except for V50 which contains the calculated Johnson-V magntude and Gaia Bp-Rp.

Unless manually selected, ASTAP will use in order of preference: D80, V50, D50, H18, H17, D20, D05. You can force a star database in ASTAP, tab alignment (ctrl+A). 

Hyperleda, is a very large galaxy database for deep sky annotation. Contains 4.970.062 objects. Based on extract from http://atlas.obs-hp.fr/hyperleda/  For macOS a 2.1 million object Hyperleda database is included with the star database. This will be overriden with the available update.

For more information see:
http://www.hnsky.org/astap.htm

The compact file format is described at:
http://www.hnsky.org/astap.htm#1476
and in the source code

Clear skies, Han


==================================================================================================
==================================================================================================
==================================================================================================
Acknowledgement of databases:

******Hyperleda.csv large galaxy database******

This is an extract from HyperLEDA  database from  http://leda.univ-lyon1.fr 

HyperLEDA is a database and a collection of tools to study the physics of galaxies and cosmology. The project, started in 1983, is currently maintained by a collaboration between Observatoire de Lyon (France) and the Special Astrophysical Observatory (Russia).

The principle behind HyperLEDA is to collect measurements published in literature and modern surveys, and to combine them into a unique homogeneous description of the astronomical objects. This enables the researcher to compare objects located at very different distances. This approach is a continuation of the famous series of Bright Galaxy Catalogues (RC1, RC2, RC3) by de Vaucouleurs and co-workers. The result of the homogenization is the Leda catalogue.

HyperLeda is not only used by researchers, but also by sky lovers or amateur astronomers interested to learn more about galaxies, by students, and by professors. HyperLeda is developed in the frame of the Virtual Observatory, an initiative intended to facilitate the exchange and usage of the data at the global scale. All the data and the software is publicly available in open-source for non-commercial purposes. 

- Paper: Makarov et al. http://adsabs.harvard.edu/abs/2014A%26A...570A..13M 
- We acknowledge the usage of the HyperLeda database (http://leda.univ-lyon1.fr



****** Star databases******

This are an extract of the Gaia star catalog release DR3 by European Space Agency  Science & Technology in a special format developed for the HNSKY planetarium program and ASTAP program . We acknowledge the usage of the Gaia database



This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national institutions, in particular the institutions participating in the Gaia Multilateral Agreement.

The LaTeX version is:

This work has made use of data from the European Space Agency (ESA) mission
{\it Gaia} (\url{https://www.cosmos.esa.int/gaia}), processed by the {\it Gaia}
Data Processing and Analysis Consortium (DPAC,
\url{https://www.cosmos.esa.int/web/gaia/dpac/consortium}). Funding for the DPAC
has been provided by national institutions, in particular the institutions
participating in the {\it Gaia} Multilateral Agreement.

If you have used Gaia EDR3 data in your research, please cite both the Gaia mission paper and the Gaia EDR3 release paper:

    •

    Gaia Collaboration et al. (2016b): The Gaia mission (provides a description of the Gaia mission including spacecraft, instruments, survey and measurement principles, and operations);
    •

    Gaia Collaboration et al. (2020b): Gaia EDR3: Summary of the contents and survey properties.

In addition, please cite (some of) the following papers that describe the data release contents and DPAC data processing and validation in more detail, as appropriate:

    •

    Riello et al. (2020): Gaia EDR3: Photometric content and validation;
    •

    Seabroke et al. (2020): Gaia EDR3: Updated radial velocities from Gaia DR2;
    •

    Torra et al. (2020): Gaia EDR3: Building the Gaia DR3 source list - Cross-match of Gaia observations;
    •

    Fabricius et al. (2020): Gaia EDR3: Catalogue validation;
    •

    Lindegren et al. (2020): Gaia EDR3: The astrometric solution;
    •

    Klioner et al. (2020): Gaia EDR3: The celestial reference frame (Gaia-CRF3);
    •

    Lindegren et al. (2020): Gaia EDR3: Parallax bias versus magnitude, colour, and position;
    •

    Rowell et al. (2020): Gaia EDR3: Modelling and calibration of Gaia’s point and line spread functions;
    •

    Marrese et al. (2020): Gaia EDR3: Cross-match with external catalogues - Algorithm and results.

For reference, the following papers describe the performance verification that DPAC has performed on Gaia EDR3:

    •

    Gaia Collaboration et al. (2020c): Gaia EDR3: The Gaia Catalogue of Nearby Stars;
    •

    Gaia Collaboration et al. (2020b): Gaia EDR3: Structure and properties of the Magellanic Clouds;
    •

    Gaia Collaboration et al. (2020a): Gaia EDR3: The Galactic anticentre;
    •

    Gaia Collaboration et al. (2020a): Gaia EDR3: Acceleration of the solar system from Gaia astrometry.

This on-line documentation has been indexed at ADS and BibTeX entries for citing individual chapters or the full documentation package as a whole can be retrieved from there.

The Gaia data are open and free to use, provided credit is given to ‘ESA/Gaia/DPAC’. In general, access to, and use of, ESA’s Gaia archive (hereafter called ‘the website’) constitutes acceptance of the following, general terms and conditions. Neither ESA nor any other party involved in creating, producing, or delivering the website shall be liable for any direct, incidental, consequential, indirect, or punitive damages arising out of user access to, or use of, the website. The website does not guarantee the accuracy of information provided by external sources and accepts no responsibility or liability for any consequences arising from the use of such data.

