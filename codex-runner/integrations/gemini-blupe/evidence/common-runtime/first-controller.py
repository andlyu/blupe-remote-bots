def run(env):
    pose = env.left.fk_world_ee()
    q = env.left.solve_arm_ik(pose[:3,3], target_rot_world=pose[:3,:3])
    env.left.move_joint(q, duration_s=.3)
    env.left.set_gripper(0., duration_s=.5)
    env.left.set_gripper(.9992793312193716, duration_s=.5)
    q = env.right.q_arm.copy()
    q[0] += .02
    env.right.move_joint(q, duration_s=.5)
    env.right.set_gripper(1., duration_s=.5)
    camera = env.camera_opencv('top')
    assert camera['rgb'].shape == (360,640,3)
    assert camera['K'].shape == (3,3)
