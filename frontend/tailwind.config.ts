import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 命中高亮色（阅卷工作台：精确命中 / 语义命中 / 部分命中）
        "hit-exact": "#bbf7d0",
        "hit-semantic": "#bfdbfe",
        "hit-partial": "#fde68a",
      },
    },
  },
  plugins: [],
};

export default config;
