# Reset gripper position closure

The size-aware profile's `--feedback-close-gap-mm 20` commands a20mm final jaw
gap for fresh and corrected cached plans, in every close and carry stage. It
preserves the60mm pregrasp and40mm release gaps for30mm blocks. The reference
conversion is gap = -1mm +95mm × normalized aperture, so20mm maps to
0.2210526316; it is not20percent aperture and is not a force target.

The previous profile requested30.1mm for a declared30mm cube. A failed pickup
recorded normalized close0.3273684211 and encoder0.3298879653, corresponding to
30.1mm and approximately30.34mm under that CAD/reference conversion. Installed
contact width and force were not measured by these aperture readings.

The native command remains20mm even when an object blocks the jaws. The offline
installed-CAD sweep uses a separate loaded-grasp hypothesis: the projected cube
width minus the existing bounded0.5mm total CAD preload, with zero relief.
For a30mm face grasp its modeled gap is29.5mm, while the command receipt remains
20mm. The audit records both minimum commanded and modeled gaps per stage.
This does not model10mm of rigid-cube deformation, silently replace the native
setpoint, or certify physical contact or force. The existing native position
interface and driver force/current/travel protections remain unchanged.

The audit preserves its original pad patch rule. It also recognizes selected
cube/active fingertip edge contact during close and carry, within the existing
2mm contact-height uncertainty in pad X/Z and the existing1mm front-plane band.
Penetration is bounded by half the modeled total preload at that sample plus
1micrometer numerical tolerance, capped by the original1mm depth limit. The
modeled nominal aperture must match its declared CAD compression and relief;
the commanded aperture must separately match the explicit close-gap setting.
At release the same bounded contact may persist only while the modeled jaws
still apply preload and the endpoint opens to at least cube width. There is no
exception for another cube, inactive tip, arm, gripper body, table, greater
penetration, or approach. Existing floor, held-cube, clearance and trajectory
checks stay in force using the modeled geometry.

Old snapshots remain immutable. Conversion, actual CLI defaults/explicit args and fresh/cached commands are
verified for the frozen release. Saved-scene CAD evidence is retained separately
and is not a required deployment gate.
These software checks do not establish a successful physical pickup, force
measurement, or broad layout qualification.
