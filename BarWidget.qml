import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "io.github.davidkaya.omarchy-scenes"

  readonly property var sceneService: bar && bar.shell
    ? bar.shell.serviceFor(moduleName)
    : null
  readonly property string icon: sceneService ? sceneService.activeIcon : "󰒓"
  readonly property string label: sceneService ? sceneService.activeName : "Scenes"
  readonly property bool compact: bar && bar.vertical

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.compact ? root.icon : root.icon + "  " + root.label
    tooltipText: sceneService && sceneService.error
      ? sceneService.error
      : "Switch desktop scene"
    foreground: sceneService && sceneService.phase === "applied-with-warnings"
      ? Color.urgent
      : (root.bar ? root.bar.foreground : Color.foreground)
    horizontalPadding: Style.spacing.controlPaddingX
    onPressed: function() {
      if (root.bar)
        root.bar.run("omarchy-shell shell toggle io.github.davidkaya.omarchy-scenes")
    }
  }
}
