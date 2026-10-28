# The compact GUI (-mini)

The window has two tabs on the left, **Tuning** (the default) and **History**,
the live plots on the right, and the action bar along the bottom.

Start it through safe-badger, which puts back every device the session changed
if Badger is interrupted:

    pixi run safe-badger mini -t 01_Linac_RIL_tuning.yaml

## Tuning tab

**Tuning Task**: pick a task (template) from the dropdown, or **From file**.
**Save as...** saves your current setup under `tuning_templates/saved/`; it will
not overwrite an operations template. Loading a task records every device it
can write, so that **Revert** can put them back.

**Parameters**: **Machine Interface** and **Optimization Algo** each open a panel
with that part's settings and an **Open Docs** button. A setting holding a list
of `{name: value}` pairs has an **Edit...** button: a table, no braces or commas
to type. A value that cannot be used is marked red, with the reason in its
tooltip, and Go refuses to start until it is fixed.

**Variables**: the devices the optimizer may change. Add one with the dropdown;
**Re-read values** reads their current values again (they also update by
themselves after Reset environment, Dial in and each point). Columns: **Saved** (the value
when the task loaded), **Current**, **Range (Δ)** (how far the optimizer may go
either side of the current value; edit it per variable, or widen or narrow
them all by about 10% with the arrows in the header). Untick a variable to leave it where it is.

A variable whose current value is outside its limits (for example a supply at
standby) is unticked with a warning when the task loads, and Go refuses to start
with it ticked: it cannot be tuned from where it is.

**Initial Points**: the first settings the run tries. **Add Current**, **Add
Random**, **Add Row** to type one, **Clear All**. A task may set its own.

**Objectives**: what to minimize or maximize. **Constraints**: limits to keep,
each with a relation and threshold; a **Critical** constraint stops the run
when it is broken. **Observables**: extra readings to record.

## History tab

Past runs, by date, newest first. Click one to show its plots and settings.
Right-click a run:

- **Continue from this run**: the next Go starts a new run that keeps all its
  points (widen a range first if the optimum looked to be past the edge).
- **Add its points**: with Continue on, add another run's points too; Go then
  shows a summary of what each run gives, with optional filters.
- **Open File**, **Open File Directory**, **File Path** (copy it).

## Action bar (left to right)

- **Delete** (trash): delete the shown run.
- **Logbook** (book): post to the logbook.
- **?**: this page.
- **Revert**: put every device back to its setting from when the task was first
  loaded.
- **Continue**: turns green when on; the next Go continues from the shown run.
- **Reset environment** (curved arrow): back to the run's starting settings.
- **Pause / Resume**.
- **Run** (green): Go. Its arrow offers **Run until**, which stops after a number
  of evaluations or a time. While running, it becomes **Stop**.
- **Checkpoint** (flag): save, edit or load a checkpoint.
- **Jump to optimum** (star): select the best point so far in the plots.
- **Dial in solution**: set the devices to the selected point.
- **Extensions** (right): extra analysis windows.

## Plots

Objectives, constraints and observables, and the variables, against iteration
(or time: **X Axis**). **Relative** shows the variables relative to their
starting values. Points from earlier runs (Continue) are drawn separately.

## Closing and interruptions

Closing the window with devices changed asks **Keep / Revert / Cancel**. If
Badger crashes or is killed, safe-badger stops it and restores; the run itself
stops within a second. `pixi run safe-badger pids` shows which process is which.
