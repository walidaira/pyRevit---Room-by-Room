# Room by Room — pyRevit Extension

A pyRevit extension that automatically creates floor plans, ceiling plans, interior elevations, and sheets for each selected room in a Revit project.

## Features

- **Room Selection** — Select rooms from a tree view grouped by level, or pick them interactively on the plan.
- **Automated View Creation** — Generate floor plans, ceiling plans, and interior elevations (N/S/E/W) per room, with configurable scales, offsets, and view templates.
- **Sheet Generation** — Create one sheet per room with automatic numbering, title block selection, and organized viewport placement.
- **Legend Placement** — Optionally place selected legends on every generated sheet.
- **4-Step Wizard UI** — A WPF wizard interface guides the user through room selection, view configuration, sheet settings, and a summary before execution.

## How It Works

The tool runs as a 4-step wizard:

1. **Select Rooms** — Choose rooms from a searchable tree (grouped by level) or pick them directly on the plan.
2. **Configure Views** — Enable/disable floor plans, ceiling plans, and elevations. Set scales, crop offsets, and assign view templates.
3. **Configure Sheets** — Choose a title block, set the sheet numbering prefix and start number, and select legends to place.
4. **Review & Create** — Review a summary of what will be created, then execute. All changes are wrapped in a single transaction group for easy undo.

## Project Structure

| File | Description |
|---|---|
| `script.py` | Main entry point and WPF wizard window |
| `RoomByRoomUI.xaml` | WPF interface definition |
| `room_collector.py` | Room collection, grouping by level, and interactive selection |
| `view_creator.py` | Creates floor plans, ceiling plans, and interior elevations |
| `sheet_creator.py` | Creates sheets and places viewports with automatic layout |
| `legend_placer.py` | Places legend views on sheets |
| `utils.py` | Unit conversions, unique name generation, and model data helpers |
| `extension.json` | pyRevit extension metadata |

## Installation

1. Clone or download this repository into your pyRevit extensions folder.
2. Reload pyRevit — the **Room by Room** button will appear under the **CAP_Tools** extension tab.

## Requirements

- [Autodesk Revit](https://www.autodesk.com/products/revit/) (2020+)
- [pyRevit](https://github.com/pyrevitlabs/pyRevit) (4.8+)

## License

This project is provided as-is for BIM automation purposes.
