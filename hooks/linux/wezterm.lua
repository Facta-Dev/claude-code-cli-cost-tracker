-- WezTerm layout for Claude Code: every "Claude" tab = a shell running `claude` on the
-- left + the all-sessions panel (session_panel.py) on the right. A click on a row of the
-- panel jumps to that session. Load it with hooks/linux/ccterm, or from your own config:
--   WEZTERM_CONFIG_FILE=/path/to/hooks/linux/wezterm.lua wezterm-gui start
--
-- Knobs (environment):
--   CCCOST_CLAUDE_CMD   command typed into the new tab        (default: claude)
--   CCCOST_PANEL_COLS   width of the panel in cells            (default: 42)
-- The panel is looked up next to this file, so the directory can live anywhere.
local wezterm = require 'wezterm'
local act = wezterm.action

local here = wezterm.config_file:match('^(.*)/[^/]+$') or wezterm.config_dir
local PANEL = here .. '/session_panel.py'
local CLAUDE_CMD = os.getenv('CCCOST_CLAUDE_CMD') or 'claude'
local PANEL_COLS = tonumber(os.getenv('CCCOST_PANEL_COLS') or '') or 42
local WORKDIR = wezterm.home_dir

local config = wezterm.config_builder()

config.scrollback_lines = 20000
config.audible_bell = 'Disabled'
config.use_fancy_tab_bar = false
config.tab_max_width = 40
config.hide_tab_bar_if_only_one_tab = false
config.initial_cols = 200
config.initial_rows = 50
config.window_close_confirmation = 'AlwaysPrompt'

-- Left pane: claude. Right pane: the panel. Focus goes back to claude.
local function open_claude_layout(claude_pane)
  claude_pane:split {
    direction = 'Right',
    size = PANEL_COLS,
    args = { 'python3', PANEL },
  }
  claude_pane:activate()
  claude_pane:send_text(CLAUDE_CMD .. '\n')
end

local function new_claude_tab(window, pane)
  local cwd = WORKDIR
  local url = pane:get_current_working_dir()
  if url and url.file_path then
    cwd = url.file_path
  end
  local _, claude_pane, _ = window:mux_window():spawn_tab { cwd = cwd }
  open_claude_layout(claude_pane)
end

wezterm.on('gui-startup', function()
  local _, pane, _ = wezterm.mux.spawn_window { cwd = WORKDIR }
  open_claude_layout(pane)
end)

config.keys = {
  -- New Claude tab (with the panel) in the current tab's directory.
  { key = 'T', mods = 'CTRL|SHIFT', action = wezterm.action_callback(new_claude_tab) },
  -- Plain shell tab, no panel, no claude.
  { key = 'Y', mods = 'CTRL|SHIFT', action = act.SpawnTab 'CurrentPaneDomain' },
}

return config
