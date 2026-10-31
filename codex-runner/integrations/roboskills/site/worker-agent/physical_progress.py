"""Public lifecycle display from the runner's observed events; no robot control."""


def lifecycle_events(state):
    result=[]
    for event in (state.get('interactions') or {}).get('events',[]):
        details=event.get('details') or {}
        kind=event.get('kind')
        if kind=='joined' or kind=='lifecycle' or (kind=='policy_timing' and details.get('stage') in ('home_observation_received','home_feedback_confirmed')):
            result.append({key:event[key] for key in ('id','timestamp','kind','message') if key in event} | {
                'details':{key:details[key] for key in ('session_id','episode_id','reason','stage','state','homed','settled','observation_reported_at') if key in details}})
    return result


def admission_event(events):
    return next((e for e in events if e.get('kind')=='lifecycle' and e.get('details',{}).get('reason')=='jetson_leased'),None)


def current_stage(state,stopped=False):
    if stopped:return 'stopping','Stopping','Stopping this BluPe run.'
    status=state.get('status')
    provider=state.get('provider') or {}
    if status=='queued':
        position=state.get('queue_position')
        reason=f' Queue position: {position}.' if isinstance(position,int) else ''
        return 'queue','Waiting for robot admission','Waiting in the normal BluPe robot queue.'+reason
    if status=='preparing':
        if admission_event(lifecycle_events(state)) or state.get('episode_id') and state.get('lease_id'):
            return 'preparing','Preparing the arms','Robot admission is complete. BluPe is preparing the arms and checking startup Home.'
        return 'submitting','Joining the robot queue','BluPe is preparing this request. Robot admission has not yet been confirmed.'
    if status=='running':
        if provider.get('pending_packet'):
            return 'moving','Moving the arms','BluPe is executing a checked packet and waiting for measured completion.'
        vision=provider.get('vision') or {}
        if vision.get('state') in ('waiting_for_camera','camera_error'):
            failed=vision['state']=='camera_error'
            detail=(vision.get('retry') or {}).get('message') or 'Waiting for a fresh measured camera observation.'
            return ('camera_unavailable' if failed else 'camera_recovery',
                    'Scene cameras unavailable' if failed else 'Refreshing scene cameras',
                    detail+' Camera reads do not repeat arm movement.')
        if provider.get('local_rejection'):
            return 'revising','Revising the command',str(provider['local_rejection'].get('reason') or 'The command was rejected locally before dispatch. RoboSkills can revise it.')
        if vision.get('state')=='requesting':
            return 'planning','Writing the Python skill','RoboSkills is waiting for its next Python decision from the model.'
        return 'observing','Checking the actual scene','RoboSkills is reading the actual cameras and measured arm state.'
    return 'recording','Saving the replay','BluPe execution ended. Saving the real camera recording.'


def task_outcome(state, stopped=False):
    """Separate runner termination, model assessment and physical qualification."""
    outcome=(state.get('provider') or {}).get('outcome') or {}
    failed=bool(state.get('error') or state.get('status') in ('error','failed','safety_aborted','disconnected')
                or outcome.get('status') in ('failed','give_up'))
    reason=str(state.get('error') or outcome.get('reason') or '').strip()[:1500]
    task=outcome.get('task_status')
    if stopped:return dict(status='cancelled',taskStatus='stopped',label='Stopped',reason='Stopped. Actual physical footage is available.',nativeScore=False)
    if failed:return dict(status='failed',taskStatus='failed',label='Execution failed',reason=reason or 'Physical execution failed; no automatic retry.',nativeScore=False)
    if task=='reported_success':label='Agent reports task completed'
    elif task=='reported_failure':label='Task not completed'
    elif task=='not_attempted' or not state.get('packets_submitted'):task='not_attempted';label='No task motion attempted'
    else:task='unverified';label='Task result unverified'
    return dict(status='finished',taskStatus=task,label=label,
                reason=reason or ('The agent ended without submitting task motion.' if task=='not_attempted' else 'Review the recording; the task result was not verified.'),
                nativeScore=False,assessmentSource='agent_report_unscored')
