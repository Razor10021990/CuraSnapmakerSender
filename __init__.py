##  Defines additional metadata for the plug-in.
#
#   Some types of plug-ins require additional metadata, such as which file types
#   they are able to read or the name of the tool they define. In the case of
#   the "OutputDevice" type plug-in, there is no additional metadata though.
from . import CuraSnapmakerSenderPlugin
from . import SnapmakerGCodeWriter

from UM.i18n import i18nCatalog
catalog = i18nCatalog("cura")

##  Lets Uranium know that this plug-in exists.
#
#   This is called when starting the application to find out which plug-ins
#   exist and what their types are. We need to return a dictionary mapping from
#   strings representing plug-in types (in this case "extension") to objects
#   that inherit from PluginObject.
#
#   \param app The application that the plug-in needs to register with.
def register(app):

    return {"extension": CuraSnapmakerSenderPlugin.CuraSnapmakerSenderPlugin(),
            "mesh_writer": SnapmakerGCodeWriter.SnapmakerGCodeWriter()}



def getMetaData():
    return {
        "mesh_writer": {
            "output": [{
                "extension": "gcode",
                "description": catalog.i18nc("@item:inlistbox", "Snapmaker G-code File"),
                "mime_type": "text/x-gcode",
                "mode": SnapmakerGCodeWriter.SnapmakerGCodeWriter.OutputMode.TextMode
            }]
        }
    }