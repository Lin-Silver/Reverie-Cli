"""Check process attribution when Windows reuses a dead parent's PID."""
from conversation_package import filter_process_rows


def test_preserves_genuine_descendants_and_equal_creation_times():
    rows=[{'pid':1,'parent':99,'created_at':10},
          {'pid':2,'parent':1,'created_at':10},
          {'pid':3,'parent':2,'created_at':20}]
    assert filter_process_rows(1,rows)==rows


def test_rejects_reused_parent_pid_and_its_descendants():
    rows=[{'pid':1,'parent':99,'created_at':10},
          {'pid':2,'parent':1,'created_at':120},
          {'pid':3,'parent':2,'created_at':20},
          {'pid':4,'parent':3,'created_at':30},
          {'pid':5,'parent':4,'created_at':40},
          {'pid':6,'parent':2,'created_at':130}]
    assert filter_process_rows(1,rows)==[rows[0],rows[1],rows[5]]


def test_removes_invalid_ancestry_independent_of_enumeration_order():
    rows=[{'pid':4,'parent':3,'created_at':30},
          {'pid':3,'parent':2,'created_at':20},
          {'pid':2,'parent':1,'created_at':120},
          {'pid':1,'parent':99,'created_at':10}]
    assert filter_process_rows(1,rows)==[rows[2],rows[3]]


def test_keeps_a_descendant_when_its_parent_exited_during_sampling():
    rows=[{'pid':1,'parent':99,'created_at':10},
          {'pid':3,'parent':2,'created_at':20}]
    assert filter_process_rows(1,rows)==rows


def test_keeps_owned_root_when_its_original_parent_pid_is_reused():
    rows=[{'pid':1,'parent':2,'created_at':10},
          {'pid':2,'parent':1,'created_at':20},
          {'pid':3,'parent':2,'created_at':30}]
    assert filter_process_rows(1,rows)==rows
