import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root

  property var shell: null
  property var manifest: null
  property var scenes: []
  property var state: ({})
  property string error: ""
  property bool busy: false
  property string operation: ""

  readonly property string pluginId: "io.github.davidkaya.omarchy-scenes"
  readonly property string pluginPath: manifest && manifest.__sourceDir
    ? String(manifest.__sourceDir)
    : Quickshell.env("HOME") + "/.config/omarchy/plugins/" + pluginId
  readonly property string executable: pluginPath + "/bin/omarchy-scenes"
  readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state"
  readonly property string statePath: stateHome + "/omarchy-scenes/state.json"
  readonly property string activeId: String(state.active || "")
  readonly property string activeName: String(state.name || "Choose a scene")
  readonly property string activeIcon: String(state.icon || "󰒓")
  readonly property string phase: String(state.phase || "idle")

  function parseOutput(raw) {
    var parsed
    try {
      parsed = JSON.parse(String(raw || "").trim())
    } catch (exception) {
      root.error = "The scenes command returned invalid data"
      return
    }

    if (parsed.error) {
      root.error = String(parsed.error)
      return
    }
    root.error = ""
    if (root.operation === "list") {
      root.scenes = parsed.scenes || []
      root.state = parsed.state || {}
    } else if (root.operation === "apply") {
      root.state = parsed
    }
  }

  function parseStateFile(raw) {
    try {
      var parsed = JSON.parse(String(raw || "").trim())
      if (parsed && typeof parsed === "object")
        root.state = parsed
    } catch (exception) {
      // The state file may not exist until the first scene is applied.
    }
  }

  function run(nextOperation, arguments_) {
    if (root.busy) return false
    root.operation = nextOperation
    commandProcess.command = [root.executable].concat(arguments_)
    root.busy = true
    commandProcess.running = true
    return true
  }

  function reload() {
    return run("list", ["list"])
  }

  function applyScene(sceneId) {
    sceneId = String(sceneId || "")
    if (!sceneId) return false
    return run("apply", ["apply", sceneId])
  }

  Process {
    id: commandProcess
    stdout: StdioCollector {
      id: output
      waitForEnd: true
      onStreamFinished: root.parseOutput(text)
    }

    onExited: function(exitCode) {
      root.busy = false
      if (exitCode !== 0 && !root.error)
        root.error = "Scene operation failed"
    }
  }

  FileView {
    path: root.statePath
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.parseStateFile(text())
  }

  IpcHandler {
    target: root.pluginId

    function reload(): string {
      return root.reload() ? "started" : "busy"
    }

    function apply(sceneId: string): string {
      return root.applyScene(sceneId) ? "started" : "busy"
    }

    function status(): string {
      return JSON.stringify({
        active: root.activeId,
        name: root.activeName,
        phase: root.phase,
        busy: root.busy,
        error: root.error
      })
    }
  }

  Component.onCompleted: reload()
}
