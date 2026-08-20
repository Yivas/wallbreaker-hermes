import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

export default defineConfig({
  site: "https://yivas.github.io",
  base: "/wallbreaker-hermes",
  integrations: [
    starlight({
      title: "Wallbreaker Hermes",
      description: "Authorized LLM red-teaming and the opt-in Hermes Agent laboratory.",
      customCss: ["./src/styles/custom.css"],
      editLink: {
        baseUrl: "https://github.com/Yivas/wallbreaker-hermes/edit/main/wiki/",
      },
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/Yivas/wallbreaker-hermes",
        },
      ],
      sidebar: [
        { label: "Overview", items: [{ label: "Home", slug: "" }] },
        {
          label: "Get started",
          items: [{ autogenerate: { directory: "getting-started" } }],
          collapsed: false,
        },
        {
          label: "Guides",
          items: [{ autogenerate: { directory: "guides" } }],
          collapsed: false,
        },
        {
          label: "Integrations",
          items: [{ autogenerate: { directory: "integrations" } }],
          collapsed: true,
        },
        {
          label: "Reference",
          items: [{ autogenerate: { directory: "reference" } }],
          collapsed: true,
        },
        {
          label: "Project",
          items: [{ autogenerate: { directory: "project" } }],
          collapsed: true,
        },
      ],
    }),
  ],
});
