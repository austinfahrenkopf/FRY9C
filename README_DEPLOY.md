# Clean dashboard deployment (SharePoint/OneDrive folder + one-click launcher)

## Target folder layout (inside your synced SharePoint/OneDrive folder)

```
FRY9C\                         <- your synced SharePoint folder
   Open Dashboard.bat          <- the ONLY thing users need to see / double-click
   _app\                       <- everything else (mark Hidden so users don't see it)
       serve.ps1               <- the PowerShell server (with save/load endpoints)
       index.html
       fry9c_hierarchy.json
       _form_by_sched.json
       fry9c_agg.parquet
       fry9c_active_1990_2009.parquet
       fry9c_active_2010_2019.parquet
       fry9c_active_2020_2031.parquet
       fry9c_hist.parquet
       custom_formulas.json     <- created automatically when a user clicks "Save formulas"
```

## Setup steps (once)

1. Create the `_app\` subfolder inside `FRY9C\` and move ALL the dashboard files into it
   (index.html, all parquets, the json files, and serve.ps1).
2. Put `Open Dashboard.bat` at the top level of `FRY9C\` (next to `_app\`, not inside it).
3. (Optional, to hide the plumbing) In a terminal in `FRY9C\`:  `attrib +h _app`
   — users then see only `Open Dashboard.bat`.
4. (Recommended) Right-click `Open Dashboard.bat` -> Send to -> Desktop (create shortcut),
   so people launch it without ever opening the folder. Rename the shortcut "FR Y-9C Dashboard".
5. OneDrive: right-click the `FRY9C` folder -> **"Always keep on this device"** so the
   parquets are stored locally (not cloud-only). Otherwise the first load has to download them.

## How it works
- Double-click the launcher -> a terminal opens running serve.ps1 -> the browser opens to
  http://localhost:8003/ automatically. Keep the terminal window open while using it.
- "Save formulas" writes `custom_formulas.json` into `_app\` (inside the synced folder), so
  OneDrive/SharePoint syncs it to your other machines and anyone who shares the folder.
- "Load formulas" / startup reads that file back.

## Updating to a new dashboard build
When the dashboard is updated, replace the files in `_app\` (index.html + parquets + json).
Keep `serve.ps1`, `Open Dashboard.bat`, and `custom_formulas.json` as they are.

## Sharing with colleagues
Share the `FRY9C` SharePoint folder with them; they each run `Open Dashboard.bat`. The
dashboard runs locally on their machine (the terminal must stay open). Saved formulas in
`custom_formulas.json` sync to everyone with folder access.

## SharePoint *page* embed
A SharePoint page cannot RUN this dashboard's JavaScript, and it cannot embed a `localhost`
URL for other users. To embed a live version on a SharePoint page you would need it served
from a real internal web URL (an internal/IIS host). With that off the table, use a
SharePoint page as a *link/front-door* to this shared folder + launcher instead.
