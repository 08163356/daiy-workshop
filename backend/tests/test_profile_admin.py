"""画像分层管理测试：CRUD、快照/回滚、整理提案（consent-first）"""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ai_config import AIConfig, UserProfile
from app.models.profile_admin import ProfileProposal, ProfileSnapshot
from app.services import profile_admin_service as svc


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (UserProfile.__table__, ProfileSnapshot.__table__, ProfileProposal.__table__,
                      AIConfig.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _add(self, category, key, value, confidence=0.3):
        self.db.add(UserProfile(category=category, key=key, value=value, confidence=confidence))
        await self.db.commit()


class CrudTests(Base):
    async def test_list_grouped(self):
        await self._add("基本信息", "城市", "深圳")
        await self._add("情绪模式", "恢复力", "打球后情绪回升")
        result = await svc.list_grouped(self.db)
        self.assertEqual(result["total"], 2)
        cats = [g["category"] for g in result["groups"]]
        self.assertIn("基本信息", cats)

    async def test_update_entry(self):
        await self._add("基本信息", "城市", "深圳")
        row = (await self.db.execute(select(UserProfile))).scalar_one()
        updated = await svc.update_entry(self.db, row.id, {"value": "深圳南山", "confidence": 0.9})
        self.assertEqual(updated.value, "深圳南山")
        self.assertEqual(updated.confidence, 0.9)

    async def test_delete_entry(self):
        await self._add("基本信息", "城市", "深圳")
        row = (await self.db.execute(select(UserProfile))).scalar_one()
        await svc.delete_entry(self.db, row.id)
        remaining = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual(remaining, [])


class SnapshotTests(Base):
    async def test_snapshot_and_rollback(self):
        await self._add("基本信息", "城市", "深圳", 0.6)
        await self._add("情绪模式", "恢复力", "打球后回升", 0.5)
        snap = await svc.snapshot_profile(self.db, "测试快照")
        self.assertEqual(snap.entry_count, 2)

        # 破坏当前画像
        await svc.delete_entry(self.db, (await self.db.execute(select(UserProfile))).scalars().first().id)
        self.assertEqual(len((await self.db.execute(select(UserProfile))).scalars().all()), 1)

        # 回滚恢复
        count = await svc.rollback_snapshot(self.db, snap.id)
        self.assertEqual(count, 2)
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual({r.key for r in rows}, {"城市", "恢复力"})
        # 回滚前自动备份了被破坏的状态
        snaps = await svc.list_snapshots(self.db)
        self.assertEqual(len(snaps), 2)


def _mock_client(contents: list[str]):
    """多次 AI 调用按顺序返回"""
    responses = [
        httpx.Response(200, json={"choices": [{"message": {"content": c}}], "usage": {}},
                       request=httpx.Request("POST", "https://example.test"))
        for c in contents
    ]
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post = AsyncMock(side_effect=responses)
    return client


class ProposalTests(Base):
    async def test_plan_does_not_write_and_apply_works(self):
        # 造碎片分类 + 重复条目；分类数需超过标准集（16）才会触发 AI 归一
        await self._add("心理模式", "恢复力", "打球后情绪回升", 0.4)
        await self._add("心理状态", "恢复力", "运动后情绪回升明显", 0.5)  # 与上一条语义重复
        await self._add("基本信息", "城市", "深圳", 0.6)
        for i in range(15):
            await self._add(f"碎片分类{i}", f"特征{i}", f"内容{i}")

        mapping = {c: "情绪模式" for c in ["心理模式", "心理状态"]}
        mapping.update({f"碎片分类{i}": "基本信息" for i in range(15)})
        mapping["基本信息"] = "基本信息"
        import json as _json
        client = _mock_client([
            _json.dumps(mapping, ensure_ascii=False),  # 分类归一
            '{"merges": []}', '{"merges": []}',  # 情绪模式/基本信息合并（本测试不关心）
        ])
        with patch("app.services.profile_admin_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.profile_admin_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            proposal = await svc.build_consolidation_plan(self.db)

        # 提案阶段不写画像
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual(len(rows), 18)
        self.assertEqual(proposal.status, "pending")
        # 分类归一计划包含全部 17 条非「基本信息」条目
        self.assertEqual(len(proposal.plan["category_changes"]), 17)

        # 执行提案
        result = await svc.apply_proposal(self.db, proposal.id)
        self.assertEqual(result["applied"]["category"], 17)
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertTrue(all(r.category in ("情绪模式", "基本信息") for r in rows))
        # 自动快照已生成
        snaps = await svc.list_snapshots(self.db)
        self.assertEqual(len(snaps), 1)

    async def test_pending_proposal_blocks_duplicate(self):
        await self._add("基本信息", "城市", "深圳")
        await self._add("基本信息", "性别", "男")
        # 分类数少于标准集，不调 AI（但仍需要配置存在）
        with patch("app.services.profile_admin_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            proposal = await svc.build_consolidation_plan(self.db)
        self.assertEqual(proposal.status, "pending")
        with self.assertRaises(ValueError):
            await svc.build_consolidation_plan(self.db)

    async def test_apply_twice_rejected(self):
        await self._add("基本信息", "城市", "深圳")
        await self._add("基本信息", "性别", "男")
        with patch("app.services.profile_admin_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            proposal = await svc.build_consolidation_plan(self.db)
        await svc.apply_proposal(self.db, proposal.id)
        with self.assertRaises(ValueError):
            await svc.apply_proposal(self.db, proposal.id)

    async def test_reject_proposal(self):
        await self._add("基本信息", "城市", "深圳")
        await self._add("基本信息", "性别", "男")
        with patch("app.services.profile_admin_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            proposal = await svc.build_consolidation_plan(self.db)
        await svc.reject_proposal(self.db, proposal.id)
        with self.assertRaises(ValueError):
            await svc.apply_proposal(self.db, proposal.id)


if __name__ == "__main__":
    unittest.main()
