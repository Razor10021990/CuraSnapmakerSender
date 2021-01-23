# CuraSnapmakerSender
Plugin for Cura which adds an Image to the exported gcode and Snapmaker-specific informateion. Additionally it serves you wtith the ability to directly send Gcode from within Cura to your Snapmaker.

# Installation
Copy the contents to a folder in the plugins directory of cura:
 1. In Cura open "Help"-Menu and click on "Show Configuration Folder".
 2. In the opened Folder open the "plugins" folder.
 3. Just in case you have my old plugin "SnapmakerGcodeWriter" installed, remove it. it is included in this Plugin.
 4. Extract the contents of the downloaded zip-file(Git-Hubs download feature) into the plugins directory.

# Usage
When you save your Gcode with the Save File functionality, you will get a new file-type called "Snapmaker Gcode". Uses this file-type to use this plugin to do the Gcode Saving, if you want to manually transfer files.

You will also get a new extension, which handles the sending to your Snapmaker. 
Additionally to the blue "Save File" button on the bottom right, you get a dropdown menu, where you can select your Snapmaker-Printer.

By default it tries to Auto-Discover your printer on the network. Just in case you want to disable Auto-Discover and or manually add printers, you can do so by opening the Settings from the Menu-Bar on the top in "Extensions/CuraSnapmakerSender/Settings".

Happy Printing!
