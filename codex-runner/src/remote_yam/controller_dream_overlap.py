"""Opt-in overlap through the installed operator's normal guarded motor owner."""
import math
import time
import numpy as np

from .dream_overlap import OverlapLoop


def run_overlap(executor, native, prepared):
    op = executor.operator
    context = executor.context
    with op.lock:
        if op._hardware_pending is not None:
            raise RuntimeError('Another native command is active')
        first = op.api_last_step + 1
    native.adapter.overlap = True

    def commanded():
        command = op._physical.last_command
        if not command:
            return None
        joints, grips = command['joints'], command['grippers']
        return {key: list(joints[offset:offset+6]) + [grips[offset//6]]
                for key, offset in (('q_l_chunk', 0), ('q_r_chunk', 6))}
    native.adapter.commanded_source = commanded

    def predict():
        # Predicted rows are not executed step IDs. Allocate IDs only at dispatch.
        points = native.adapter.build_trajectory(prepared['task'], native.observation(), 0)
        probe = native.adapter.last_probe or {}
        origin = probe['input_monotonic']
        index = max(0, math.floor((time.monotonic()-origin)*10))
        if index < len(points):
            snapshot = op._physical.snapshot()
            start = snapshot.left.joints_rad + snapshot.right.joints_rad
            targets = tuple(tuple(math.radians(v) for side in ('left', 'right')
                                  for v in row[side+'_joints_deg']) for row in points[index:])
            # Validate the remaining plan before installing it, then validate
            # each selected point again against live native feedback at dispatch.
            op._safety_guardrails.approve(np.asarray(start), targets, cadence_hz=10,
                                         target_limit_tolerance_rad=.001)
        return points, origin

    def validate(index, previous, waypoint):
        if executor._cancelled():
            raise RuntimeError('Dream overlap lease ended')
        approved = op._safety_guardrails.approve(np.asarray(previous), (waypoint,), cadence_hz=10,
                                                target_limit_tolerance_rad=.001)
        return tuple(approved.waypoints[0])

    def play(point):
        if executor._cancelled():
            return
        q = tuple(math.radians(v) for side in ('left', 'right')
                  for v in point[side+'_joints_deg'])
        grips = (point['left_gripper'], point['right_gripper'])

        def progress(index):
            with op.lock:
                if executor._cancelled():
                    return
                op.api_last_step += 1
                op.api_observation_step = op.api_last_step + 1
                op.policy_phase = 'dream_overlap'
            with executor.lock:
                executor.waypoints += 1

        # The same driver, health checks, runtime geometry guard, command clock,
        # cancellation and recorder command source as ordinary trajectories.
        # Each point retains its 100 ms slot; no inter-chunk settle is requested.
        op._physical.execute((q,), cadence_hz=10, gripper_waypoints=(grips,),
            validate_waypoint=validate, on_waypoint=progress,
            wait_for_settle=False, disable_on_settle_timeout=False,
            cancel_event=native.cancel)

    def predicted(**details):
        with executor.lock:
            executor.predictions = details['predictions']
            executor.predicted_waypoints += (native.adapter.last_probe or {}).get('waypoint_count', 0)

    loop = OverlapLoop(predict=predict, play=play, cancelled=executor._cancelled,
                       budget=native.adapter._max_commands-first, on_prediction=predicted)
    with executor.lock:
        executor.overlap_loop = loop
        executor.state = 'executing_overlap'
    try:
        loop.run()
    finally:
        # Inference may still be unwinding; invalidate its transport before a
        # visitor can reuse the resident SDK handle or its smoothing history.
        native.cancel.set()
        native.adapter.close_transport()
        if loop.thread is not None:
            loop.thread.join(3)
            if loop.thread.is_alive():
                raise RuntimeError('Dream overlap predictor did not release its worker')
