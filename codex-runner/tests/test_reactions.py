from remote_yam.reactions import Reactions


def test_expiry_capacity_and_room_isolation():
    now = [100.0]
    room, other = Reactions(lambda: now[0]), Reactions(lambda: now[0])
    for _ in range(140):
        room.publish('🙂', 'visitor')
    assert len(room.snapshot()) == 128
    assert other.snapshot() == []
    assert room.snapshot()[0]['id'] == 13
    now[0] += 4.5
    assert room.snapshot()[0]['remaining_ms'] == 500
    now[0] += .5
    assert room.snapshot() == []
    assert room.publish('😠', 'visitor')['id'] == 141
    assert Reactions().snapshot() == []  # Restart has no reaction history.
