import UM 1.1 as UM
import QtQuick 2.2 
import QtQuick.Controls 1.1
import QtQuick.Layouts 1.3
import QtQml.Models 2.3

UM.Dialog //Creates a modal window that pops up above the interface.
{
    property variant i18n_catalog: UM.I18nCatalog { name: "cura"; }
    id: base
    flags: Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint
    //minimumWidth: 320 * screenScaleFactor
    //minimumHeight: 350 * screenScaleFactor
    //maximumWidth : 320 * screenScaleFactor
    //width : 500 * screenScaleFactor
    title: "Settings for SnapmakerPlugin"
    closeOnAccept : true

    onAccepted:{
        if (autoDiscoveryCheckbox.checkedState == Qt.Checked) {
            manager.autodiscover = true
        } else {
            manager.autodiscover = false
        }
        manager.saveSettings()
        manager.managePrinters()
    }
    
   
    ColumnLayout{
        id: topLayout
        spacing: 4 * screenScaleFactor
        width: base.width - 20 * screenScaleFactor
        height : base.height - 20 *screenScaleFactor
            Label //Creates a bit of text.
            {
                text : i18n_catalog.i18nc("@settings:description", "Auto-Discovery tries to find your Snapmaker on your network:")
            }
        
            CheckBox {
                id: autoDiscoveryCheckbox
                partiallyCheckedEnabled : false
                text:"Auto-Discovery"
                checked : manager.autodiscover
            }
            Label 
            {
                text : i18n_catalog.i18nc("@settings:description", "You can manually define printers in the following table:")
            }
            RowLayout{
                spacing: 2.0
                Button{
                    text: i18n_catalog.i18nc("@action:button", "Add")
                    onClicked: {
                        manager._appendEmptyPrinter()
                    }
                }

                Button{
                    text: i18n_catalog.i18nc("@action:button", "Remove")
                    property var i
                    onClicked:
                    {
                        if( table.currentRow != -1){
                            i = 0
                            for (i=0;i<table.rowCount;i++){
                                if(table.selection.contains(i)){
                                    manager._removePrinterfromList(table.currentRow)
                                }
                            }
                            table.selection.clear()
                        }
                    }
                }

            }
            
            

            TableView {
                id : table
                TableViewColumn { role: "name"; title: i18n_catalog.i18nc("@tablecolumn", "Name"); width: 200 * screenScaleFactor}
                TableViewColumn { role: "address"; title: i18n_catalog.i18nc("@tablecolumn", "Address(IPv4,IPv6,Hostname)");  width: 200 * screenScaleFactor}
                //height : 600 * screenScaleFactor
                //width : 600 * screenScaleFactor
                Layout.alignment: Qt.AlignLeft
                //Layout.preferredWidth: 600 * screenScaleFactor
                //Layout.preferredHeight: 600 * screenScaleFactor
                Layout.fillHeight : true
                Layout.fillWidth : true
                selectionMode: SelectionMode.ExtendedSelection
                model: manager.machines
                itemDelegate: {
                return editableDelegate;
                }
            }
            Component {
                id: editableDelegate
                Item {

                    Text {
                        width: parent.width
                        anchors.margins: 4
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        elide: styleData.elideMode
                        text: styleData.value !== undefined ? styleData.value : ""
                        color: styleData.textColor
                        visible: !styleData.selected
                    }
                    Loader { 
                        id: loaderEditor
                        anchors.fill: parent
                        anchors.margins: 4
                        Connections {
                            target: loaderEditor.item
                            onEditingFinished : {
                                manager.machines.setProperty(styleData.row, styleData.role, loaderEditor.item.text)
                                loaderEditor.deselect()
                            }
                        }
                        sourceComponent: styleData.selected ? editor : null
                        Component {
                            id: editor
                            TextInput {
                                id: textinput
                                color: styleData.textColor
                                text: styleData.value
                                MouseArea {
                                    id: mouseArea
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: textinput.forceActiveFocus()
                                }
                            }
                        }
                    }
                }
            }
            
            Button
            {
                id: testButton
                text: "Close"
                Layout.alignment : Qt.AlignRight
                onClicked: {
                    //manager.machines = globalList.model
                    base.accept()
                }
            }
        
    }
}