from contextops_lab.cli import build_parser
from contextops_lab.redis_drill import LABEL


def test_durable_store_drill_cli_contract():
    args = build_parser().parse_args(["durable-store-drill"])
    assert args.redis_server == "redis-server"
    assert args.output_dir == "artifacts/redis-drill"
    assert LABEL == "local_real_redis_restart_drill"
