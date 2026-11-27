// The CLI component has its own profile and does not acquire the desktop shell's lock.
if (process.argv.includes("--reverie-browser-host")) {
  require("./browser-component");
} else {
  require("./main");
}
