"""RoboSkills absolute tool-frame selection over the unchanged native packet path."""
from numbers import Real
import numpy as np
from .robocurve_trajectory import ARMS, InvalidMove, RoboCurveTrajectory


def tool_rotation(value):
    """Rows encode base-frame tool axes; columns X/Y/Z are opening/side/approach.

    Accept floating-point SO(3) error up to1e-8 without normalization. This is
    matrix arithmetic tolerance, not a joint/workspace/actuator limit change.
    """
    try:
        raw=np.asarray(value,dtype=object)
        if raw.shape!=(3,3) or any(isinstance(x,(bool,np.bool_)) or not isinstance(x,Real) for x in raw.flat):
            raise ValueError
        matrix=np.asarray(raw,dtype=float)
        if (not np.isfinite(matrix).all() or np.any(np.abs(matrix)>1.)
                or not np.allclose(matrix.T@matrix,np.eye(3),rtol=0,atol=1e-8)
                or abs(float(np.linalg.det(matrix))-1)>1e-8):
            raise ValueError
    except (TypeError,ValueError,OverflowError):
        raise InvalidMove('rotation must be a finite3x3 proper orthonormal matrix (determinant+1); use precise np.sin/cos, not rounded or reflected axes','invalid_rotation') from None
    return matrix.copy()


def base_point(value):
    try:
        raw=np.asarray(value,dtype=object)
        if raw.shape!=(3,) or any(isinstance(x,(bool,np.bool_)) or not isinstance(x,Real) for x in raw.flat):
            raise ValueError
        point=np.asarray(raw,dtype=float)
        if not np.isfinite(point).all():raise ValueError
    except (TypeError,ValueError,OverflowError):
        raise ValueError('Approach points must be finite[x,y,z] metre lists in the named arm base') from None
    return point


class RoboSkillsTrajectory(RoboCurveTrajectory):
    """Only RoboSkills gains rotation=; the RoboCurve public contract stays intact."""
    def build(self,targets,observation,first_step_id,*,attitude=None,rotation=None):
        if rotation is None:
            return super().build(targets,observation,first_step_id,attitude=attitude)
        if attitude is not None:
            raise InvalidMove('Choose rotation or attitude, not both','invalid_rotation')
        if not isinstance(rotation,dict) or not rotation or any(arm not in ARMS for arm in rotation):
            raise InvalidMove('rotation must map named left/right arms to3x3 base-frame matrices','invalid_rotation')
        if not isinstance(targets,dict) or not targets:
            raise InvalidMove('rotation requires an explicit Cartesian position target for each named arm','invalid_rotation')
        matrices={arm:tool_rotation(value) for arm,value in rotation.items()}
        for arm in matrices:
            if not any(arm+'_'+axis in targets for axis in ('x','y','z')):
                raise InvalidMove('rotation needs a named Cartesian position target; gripper-only moves hold measured joints','invalid_rotation')
            if any(arm+'_'+axis in targets for axis in ('yaw','pitch','roll')):
                raise InvalidMove('Absolute rotation cannot be combined with relative yaw/pitch/roll targets for that arm','invalid_rotation')
        self.observe(observation)
        previous=self.start_rotations
        modes=self.attitude_references
        self.start_rotations=tuple(matrices.get(arm,previous[i]).copy() for i,arm in enumerate(ARMS))
        self.attitude_references={arm:'base_rotation' if arm in matrices else modes[arm] for arm in ARMS}
        # This explicitly selects an absolute frame, rather than retaining the
        # measured yaw expressed in a newly selected frame. Existing Euler
        # interpolation, native joint limits, inactive-arm hold and canonical
        # packet validation are unchanged.
        absolute=dict(targets)
        for arm in matrices:
            absolute.update({arm+'_'+axis:0. for axis in ('yaw','pitch','roll')})
        try:
            return self._build(absolute,observation,first_step_id)
        except Exception:
            self.start_rotations,self.attitude_references=previous,modes
            raise


def rotation_error_degrees(actual,expected):
    relative=np.asarray(actual)@np.asarray(expected).T
    cosine=(float(np.trace(relative))-1)/2
    sine=np.linalg.norm([relative[2,1]-relative[1,2],relative[0,2]-relative[2,0],relative[1,0]-relative[0,1]])/2
    return float(np.rad2deg(np.arctan2(sine,np.clip(cosine,-1.,1.))))
