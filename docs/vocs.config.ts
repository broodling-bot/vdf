import { defineConfig } from "vocs/config";

export default defineConfig({
  title: "VDF",
  titleTemplate: "%s · VDF Docs",
  description:
    "Wesolowski VDF + RSW timelock decryption for Starknet — a provable Cairo executable.",
  accentColor: "light-dark(#0e7490, #22d3ee)",
  topNav: [
    { text: "Guide", link: "/", match: "/" },
    { text: "GitHub", link: "https://github.com/broodling-bot/vdf" },
  ],
  sidebar: [
    {
      text: "Start here",
      items: [
        { text: "Overview", link: "/" },
        { text: "How it works", link: "/how-it-works" },
      ],
    },
    {
      text: "Core concepts",
      items: [
        { text: "RSW timelock", link: "/concepts/rsw-timelock" },
        { text: "Wesolowski VDF", link: "/concepts/wesolowski-vdf" },
        { text: "Cairo bigint", link: "/concepts/cairo-bigint" },
      ],
    },
    {
      text: "Using the repo",
      items: [
        { text: "Quick start", link: "/guide/quickstart" },
        { text: "Proving pipeline", link: "/guide/proving" },
        { text: "Reproducing vectors", link: "/guide/vectors" },
      ],
    },
    {
      text: "Integration",
      items: [
        { text: "Whisper sealed-bid auctions", link: "/integration/whisper" },
      ],
    },
  ],
});
