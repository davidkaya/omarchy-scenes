import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui

Item {
  id: root

  property bool opened: false
  property var shell: null
  property int selectedIndex: 0

  readonly property string pluginId: "io.github.davidkaya.omarchy-scenes"
  readonly property var sceneService: shell ? shell.serviceFor(pluginId) : null
  readonly property var scenes: sceneService ? sceneService.scenes : []

  function open(payloadJson) {
    root.opened = true
    var requested = ""
    try {
      requested = String(JSON.parse(String(payloadJson || "{}")).scene || "")
    } catch (exception) {
      requested = ""
    }
    if (requested) {
      for (var index = 0; index < root.scenes.length; index++) {
        if (root.scenes[index].id === requested) {
          root.selectedIndex = index
          break
        }
      }
    }
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    if (!root.opened) return
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide(root.pluginId)
  }

  function applyIndex(index) {
    if (!root.sceneService || index < 0 || index >= root.scenes.length) return
    root.selectedIndex = index
    root.sceneService.applyScene(root.scenes[index].id)
  }

  function moveSelection(delta) {
    if (!root.scenes.length) return
    root.selectedIndex = (root.selectedIndex + delta + root.scenes.length) % root.scenes.length
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "omarchy-scenes"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: root.opened
      ? WlrKeyboardFocus.Exclusive
      : WlrKeyboardFocus.None

    Rectangle {
      anchors.fill: parent
      color: Color.menu.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.close()
    }

    BorderSurface {
      id: card
      width: Math.min(Style.space(520), panel.width - Style.gapsOut * 2)
      height: Math.min(content.implicitHeight + Style.spacing.panelPadding * 2,
                       panel.height - Style.gapsOut * 2)
      anchors.centerIn: parent
      color: Color.menu.background
      radius: Style.cornerRadius
      borderSpec: Border.surfaceSpec(
        "menu", "border", Color.menu.border, Math.max(1, Style.space(1)))
      padding: Style.spacing.panelPadding

      MouseArea {
        anchors.fill: parent
        onClicked: function(mouse) { mouse.accepted = true }
      }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape || event.key === Qt.Key_Q) {
            root.close()
            event.accepted = true
          } else if (event.key === Qt.Key_Up || event.key === Qt.Key_K) {
            root.moveSelection(-1)
            event.accepted = true
          } else if (event.key === Qt.Key_Down || event.key === Qt.Key_J) {
            root.moveSelection(1)
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                     || event.key === Qt.Key_Space) {
            root.applyIndex(root.selectedIndex)
            event.accepted = true
          } else if (event.key === Qt.Key_R && root.sceneService) {
            root.sceneService.reload()
            event.accepted = true
          }
        }
      }

      Column {
        id: content
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        spacing: Style.spacing.panelGap

        Row {
          width: parent.width
          spacing: Style.spacing.controlGap

          Text {
            text: "󰒓"
            color: Color.accent
            font.family: Style.font.family
            font.pixelSize: Style.font.display
          }

          Column {
            width: parent.width - parent.children[0].implicitWidth - parent.spacing
            spacing: Style.spacing.xs

            Text {
              text: "Scenes"
              color: Color.menu.text
              font.family: Style.font.family
              font.pixelSize: Style.font.heading
              font.bold: true
            }
            Text {
              text: root.sceneService && root.sceneService.busy
                ? "Applying " + root.sceneService.activeName + "…"
                : "Choose a desktop context"
              color: Color.menu.text
              opacity: 0.55
              font.family: Style.font.family
              font.pixelSize: Style.font.bodySmall
            }
          }
        }

        PanelSeparator {
          width: parent.width
          foreground: Color.menu.text
        }

        Text {
          visible: !root.sceneService || root.scenes.length === 0
          width: parent.width
          text: root.sceneService && root.sceneService.error
            ? root.sceneService.error
            : "No scenes found. Edit ~/.config/omarchy/scenes.json."
          color: Color.urgent
          wrapMode: Text.WordWrap
          font.family: Style.font.family
          font.pixelSize: Style.font.body
        }

        Repeater {
          model: root.scenes

          Rectangle {
            id: row
            required property var modelData
            required property int index

            width: content.width
            height: Style.space(58)
            radius: Style.cornerRadius
            color: index === root.selectedIndex
              ? Style.hoverFillFor(Color.menu.text, Color.accent)
              : "transparent"

            readonly property bool active: root.sceneService
              && root.sceneService.activeId === String(modelData.id)

            Row {
              anchors.fill: parent
              anchors.leftMargin: Style.spacing.rowPaddingX
              anchors.rightMargin: Style.spacing.rowPaddingX
              spacing: Style.spacing.controlGap

              Text {
                anchors.verticalCenter: parent.verticalCenter
                text: String(row.modelData.icon || "󰒓")
                color: row.active ? Color.accent : Color.menu.text
                font.family: Style.font.family
                font.pixelSize: Style.font.iconLarge
              }

              Column {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - parent.children[0].implicitWidth
                       - status.implicitWidth - parent.spacing * 2
                spacing: Style.spacing.xs

                Text {
                  width: parent.width
                  text: String(row.modelData.name)
                  color: Color.menu.text
                  elide: Text.ElideRight
                  font.family: Style.font.family
                  font.pixelSize: Style.font.subtitle
                  font.bold: row.active
                }
                Text {
                  width: parent.width
                  text: String(row.modelData.description || "")
                  color: Color.menu.text
                  opacity: 0.5
                  elide: Text.ElideRight
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                }
              }

              Text {
                id: status
                anchors.verticalCenter: parent.verticalCenter
                text: row.active ? "ACTIVE" : ""
                color: Color.accent
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: true
              }
            }

            MouseArea {
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: root.selectedIndex = row.index
              onClicked: root.applyIndex(row.index)
            }
          }
        }

        Text {
          visible: root.sceneService
            && (root.sceneService.error || root.sceneService.phase === "applied-with-warnings")
          width: parent.width
          text: root.sceneService && root.sceneService.error
            ? root.sceneService.error
            : "Applied with warnings. Run omarchy-scenes status for details."
          color: Color.urgent
          wrapMode: Text.WordWrap
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
        }

        Text {
          width: parent.width
          horizontalAlignment: Text.AlignRight
          text: "↑↓ select  ·  enter apply  ·  r reload  ·  esc close"
          color: Color.menu.text
          opacity: 0.4
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
