import UM 1.6 as UM
import Cura 1.6 as Cura

import QtQuick 6.2
import QtQuick.Controls 6.2
import QtQuick.Layouts 6.2

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
            UM.Label //Creates a bit of text.
            {
                text : i18n_catalog.i18nc("@settings:description", "Auto-Discovery tries to find your Snapmaker on your network:")
            }
        
            UM.CheckBox {
                id: autoDiscoveryCheckbox
                //partiallyCheckedEnabled : false
                text:"Auto-Discovery"
                checked : manager.autodiscover
            }
            UM.Label 
            {
                text : i18n_catalog.i18nc("@settings:description", "You can manually define printers in the following table:")
            }
            RowLayout{
                spacing: 2.0
                UM.Button{
                    text: i18n_catalog.i18nc("@action:button", "Add")
                    onClicked: {
                        manager._appendEmptyPrinter()
                    }
                }

                UM.Button{
                    text: i18n_catalog.i18nc("@action:button", "Remove")
                    property var i
                    onClicked:
                    {
                        if( table.currentRow >= 0 && table.currentRow < manager.machines.count){
                            manager._removePrinterfromList(table.currentRow)
                            //table.selection.clear()
                        }
                    }
                }

            }
            
            

            TableView {
                id : table
                //TableViewColumn { role: "name"; title: i18n_catalog.i18nc("@tablecolumn", "Name"); width: 200 * screenScaleFactor}
                //TableViewColumn { role: "address"; title: i18n_catalog.i18nc("@tablecolumn", "Address(IPv4,IPv6,Hostname)");  width: 200 * screenScaleFactor}
                //contentHeight : 600 * screenScaleFactor
                //contentWidth : 600 * screenScaleFactor
                /*height: 600 * screenScaleFactor
                width : 600 * screenScaleFactor
                Layout.alignment: Qt.AlignLeft
                Layout.preferredWidth: 600 * screenScaleFactor
                Layout.preferredHeight: 600 * screenScaleFactor
                */
                property var columnWidths: [100, 100]
                columnWidthProvider: function (column) { return columnWidths[column] }
                rowHeightProvider: function (row) { return 50}
                Layout.fillHeight : true
                Layout.fillWidth : true
                 //property var modelRows: manager._manualprinters
                 ScrollBar.vertical: UM.ScrollBar {
                    id: scrollBar
                    policy: ScrollBar.AlwaysOn
                }
                selectionModel: ItemSelectionModel {
                    model: manager
                }
                model: manager
                delegate: editableDelegate
            }
            Component {
                id: editableDelegate
                
                Item {
                    required property bool selected
                    Text {
                        width: parent.width
                        anchors.margins: 4
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        //elide: styleData.elideMode
                        text: display
                        //color: styleData.textColor
                        visible: !selected
                    }
                    Loader { 
                        id: loaderEditor
                        anchors.fill: parent
                        anchors.margins: 4
                        Connections {
                            target: loaderEditor.item
                            onEditingFinished : {
                                manager.setData(index, 2, loaderEditor.item.text)
                                loaderEditor.deselect()
                            }
                        }
                        sourceComponent: selected ? editor : null
                        Component {
                            id: editor
                            TextInput {
                                id: textinput
                                //color: styleData.textColor
                                text: edit
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
            
            UM.Button
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