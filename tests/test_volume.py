import subprocess
import unittest
from unittest.mock import Mock

from cybermint_hud.volume import PactlVolume, clamp_percent, parse_mute, parse_volume


SAMPLE_VOLUME = "Volume: front-left: 65536 / 100% / 0.00 dB, front-right: 58982 / 90% / -1.00 dB"


class VolumeTests(unittest.TestCase):
    def test_parser_reads_channel_percentages_and_mute_state(self):
        self.assertEqual(parse_volume(SAMPLE_VOLUME), 95)
        self.assertTrue(parse_mute("Mute: yes\n"))
        self.assertFalse(parse_mute("Mute: no\n"))

    def test_invalid_pactl_responses_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "no volume percentage"):
            parse_volume("Volume: unknown")
        with self.assertRaisesRegex(ValueError, "no mute state"):
            parse_mute("unknown")

    def test_values_are_clamped_to_zero_through_one_hundred(self):
        self.assertEqual(clamp_percent(-12), 0)
        self.assertEqual(clamp_percent(123), 100)
        self.assertEqual(clamp_percent(37.6), 38)

    def test_read_and_set_use_argument_lists_without_a_shell(self):
        runner = Mock(side_effect=[
            subprocess.CompletedProcess([], 0, SAMPLE_VOLUME, ""),
            subprocess.CompletedProcess([], 0, "Mute: no\n", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, SAMPLE_VOLUME, ""),
            subprocess.CompletedProcess([], 0, "Mute: yes\n", ""),
        ])
        volume = PactlVolume(run=runner, which=lambda name: "/usr/bin/pactl")
        self.assertEqual(volume.read().value, 95)
        result = volume.set_volume(140)
        self.assertEqual(result.value, 95)
        self.assertEqual(runner.call_args_list[2].args[0], ["/usr/bin/pactl", "set-sink-volume", "@DEFAULT_SINK@", "100%"])
        self.assertFalse(runner.call_args_list[2].kwargs["shell"])

    def test_missing_or_failed_tool_returns_unavailable_reason(self):
        absent = PactlVolume(which=lambda _name: None).read()
        failed = PactlVolume(
            run=lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "no default sink"),
            which=lambda _name: "/usr/bin/pactl",
        ).read()
        self.assertIsNone(absent.value)
        self.assertIn("not installed", absent.error)
        self.assertIsNone(failed.value)
        self.assertIn("no default sink", failed.error)


if __name__ == "__main__":
    unittest.main()
