import plistlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / "scripts/launchd/com.polyhermes.future-btc5m-tunnel.plist"
ASSISTANT_PLIST = ROOT / "scripts/launchd/com.polyhermes.future-btc5m-assistant.plist"


class FutureTunnelLaunchdTest(unittest.TestCase):
    def config(self):
        return plistlib.loads(PLIST.read_bytes())

    def test_login_and_all_exit_types_are_supervised_without_orphaning_ssh(self):
        config = self.config()
        self.assertIs(config["KeepAlive"], True)
        self.assertIs(config["RunAtLoad"], True)
        self.assertIs(config["AbandonProcessGroup"], False)
        self.assertEqual(15, config["ThrottleInterval"])

    def test_agent_uses_only_existing_guarded_transport_and_local_proxy(self):
        config = self.config()
        self.assertEqual("com.polyhermes.future-btc5m-tunnel", config["Label"])
        self.assertEqual(["/bin/bash", str(ROOT / "scripts/start-future-btc5m-tunnel.sh"),
                          "--remove-stale-socket", "--socks-proxy", "127.0.0.1:7890"],
                         config["ProgramArguments"])
        self.assertEqual(str(ROOT), config["WorkingDirectory"])
        self.assertEqual({"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, config["EnvironmentVariables"])
        for key in ("StandardOutPath", "StandardErrorPath"):
            self.assertEqual(ROOT / "reports/future-btc5m-assistant/tunnel" / Path(config[key]).name,
                             Path(config[key]))

    def test_assistant_dependency_is_supervised_and_uses_its_dedicated_runtime(self):
        config = plistlib.loads(ASSISTANT_PLIST.read_bytes())
        self.assertEqual("com.polyhermes.future-btc5m-assistant", config["Label"])
        self.assertEqual([str(ROOT / "scripts/future-btc5m-runtime/.venv/bin/python"),
                          str(ROOT / "scripts/future_btc5m_assistant.py"), "--watch"], config["ProgramArguments"])
        self.assertIs(config["RunAtLoad"], True)
        self.assertIs(config["KeepAlive"], True)
        self.assertIs(config["AbandonProcessGroup"], False)
        self.assertEqual(15, config["ThrottleInterval"])
        self.assertEqual(str(ROOT), config["WorkingDirectory"])
        self.assertEqual({"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                          "HTTP_PROXY": "http://127.0.0.1:7890", "HTTPS_PROXY": "http://127.0.0.1:7890",
                          "ALL_PROXY": "socks5://127.0.0.1:7890"}, config["EnvironmentVariables"])
        for key in ("StandardOutPath", "StandardErrorPath"):
            self.assertEqual(ROOT / "reports/future-btc5m-assistant/service" / Path(config[key]).name,
                             Path(config[key]))


if __name__ == "__main__":
    unittest.main()
