"""
Anima — Test Fixtures
"""

import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir():
    """创建临时数据目录，测试完成后清理"""
    d = Path(tempfile.mkdtemp(prefix="anima_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def memory_store(tmp_data_dir):
    """创建临时 MemoryStore 实例"""
    from anima.memory.store import MemoryStore
    return MemoryStore(tmp_data_dir / "memory.db")


@pytest.fixture
def memory_manager(memory_store):
    """创建 MemoryManager 实例"""
    from anima.memory.manager import MemoryManager
    return MemoryManager(memory_store)


@pytest.fixture
def trust_system(tmp_data_dir):
    """创建 TrustSystem 实例"""
    from anima.trust.system import TrustSystem
    return TrustSystem(tmp_data_dir)


@pytest.fixture
def evolution_engine(tmp_data_dir):
    """创建 EvolutionEngine 实例"""
    from anima.evolution.engine import EvolutionEngine
    engine = EvolutionEngine(tmp_data_dir)
    engine.initialize()
    return engine


@pytest.fixture
def question_tree(tmp_data_dir):
    """创建 QuestionTree 实例"""
    from anima.question.tree import QuestionTree
    tree = QuestionTree(tmp_data_dir)
    tree.initialize()
    return tree
