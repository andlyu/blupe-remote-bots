"""Meaningful attention intervention/parity tests without a checkpoint/GPU."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

torch = pytest.importorskip('torch')
spec = importlib.util.spec_from_file_location('cag_guidance', Path(__file__).parents[1] / 'examples/cag_molmoact2/guidance.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def fixture():
    def original(q, k, v, *, attn_mask=None):
        return torch.nn.functional.scaled_dot_product_attention(q.transpose(1,2), k.transpose(1,2), v.transpose(1,2), attn_mask=attn_mask).transpose(1,2)
    blocks = [SimpleNamespace(cross_attn=SimpleNamespace(_attention=original)) for _ in range(36)]
    guide = g.Guidance(SimpleNamespace(model=SimpleNamespace(action_expert=SimpleNamespace(blocks=blocks))))
    guide.install()
    torch.manual_seed(42)
    return guide, blocks, original, torch.randn(1,3,2,4), torch.randn(1,8,2,4), torch.randn(1,8,2,4)


def test_zero_exact_and_nonzero_text_only_no_cache_mutation():
    guide, blocks, original, q,k,v = fixture()
    pristine_k, pristine_v = k.clone(), v.clone()
    expected = original(q,k,v)
    with guide.request('guided',0):
        assert torch.equal(blocks[0].cross_attn._attention(q,k,v),expected)
    with guide.request('guided',.15):
        guide.active.update(indices=[3,4,5,6],context_length=8)
        result = blocks[0].cross_attn._attention(q,k,v)
    assert not torch.equal(result,expected)
    assert torch.equal(k,pristine_k) and torch.equal(v,pristine_v)
    assert guide.last_receipt['non_goal_kv_unchanged']
    assert guide.last_receipt['scaled_text_tokens']==1
    assert guide.last_receipt['kv_delta_l1']>0
    assert guide.active is None


def test_error_clears_request_and_next_baseline_is_pristine():
    guide, blocks, original, q,k,v=fixture()
    with pytest.raises(ValueError), guide.request('guided',.15):
        blocks[0].cross_attn._attention(q,k,v)
    with guide.request('baseline',0):
        assert torch.equal(blocks[0].cross_attn._attention(q,k,v), original(q,k,v))


@pytest.mark.parametrize('payload',[{'guidance_strength':True},{'guidance_strength':float('nan')},{'guidance_strength':.31},{'seed':False},{'mode':'other'}])
def test_invalid_options(payload):
    with pytest.raises(ValueError): g.options(payload)


def test_mask_uses_actual_expansion_and_fails_ambiguous():
    text='The task is to pick up cup. The setup is x'
    encoded=SimpleNamespace(ids=[1,2,3],offsets=[(0,15),(15,26),(26,len(text))])
    assert g.task_indices(text,'pick up cup',encoded,[99,99,1,2,3])==[3]
    with pytest.raises(ValueError):
        g.task_indices(text,'pick up cup',encoded,[2,2])
