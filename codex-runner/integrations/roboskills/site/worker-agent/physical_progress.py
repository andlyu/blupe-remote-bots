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
        if provider.get('vision',{}).get('state')=='requesting':
            return 'planning','Writing the Python skill','RoboSkills is waiting for its next Python decision from the model.'
        return 'observing','Checking the actual scene','RoboSkills is reading the actual cameras and measured arm state.'
    return 'recording','Saving the replay','BluPe execution ended. Saving the real camera recording.'
