MacOS 64 bit version (X86_64).  For the M1 version see below.

Download the astap.pkg installer
Use right mouse button and open the .pkg file with installer. 

If internet access results in a missing openssl message then additionally install the openssl installer from the ASTAP webpage.

On Sequoia 15.1, you can no longer right click on the package and override MacOS complaining about it being from an unknown developer. You'll need to go into System Settings->Privacy & Security and scroll to the bottom and select astap.pkg to allow installation. You could also remove the extende attributes from the file like (untested):
   xattr -cr  astap.pkg
  or
   xattr -cr  astap_M1.pkg


MacOS 64 bit version (Apple silicon processor, M-types cpu).  Code signing of the executable is required.  Instructions:

1) Download
https://sourceforge.net/projects/astap-program/files/macOS%20installer/astap_M1.pkg/download

2) Make sure the ASTAP program is not running. Place the mouse cursor on the pkg file and install using the right mouse button popup menu.

3) Open a terminal windows and copy paste and execute the following command:
codesign --force -s - /Applications/ASTAP.app/Contents/MacOS/astap

The code signing is required only once. An update doesn't require code signing.


For astrometric solving download and install also one of the star databases based on your field-of-view (fov):

     D80      (6 > fov > 0.15 degrees)
     D50      (6 > fov > 0.2 degrees)
     D20      (6 > fov > 0.3 degrees) 
     D05      (6 > fov > 0.6 degrees) 
     G05      (20 > fov > 3.0 degrees) 
     W08      (     fov > 20 degrees) 


Other special versions:

astap_command-line_version.zip is a command-line version for astrometric solving only.  Command line parameters for the command-line version are identical to the GUI version. The command-line version can process FITS, JPEG, PNG, PPM and TIFF files but not RAW and XISF files.

