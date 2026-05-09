export const SITE = {
  website: "https://my-trip-note.com/",
  /** Google Analytics 4 の測定ID（未使用時は空文字にする） */
  googleAnalyticsMeasurementId: "G-JDX3Z4FR0L",
  author: "Kensuke",
  profile: "https://my-trip-note.com/about/",
  desc: "旅・挑戦・日々の記録",
  title: "my trip note",
  ogImage: "astropaper-og.jpg",
  lightAndDarkMode: true,
  postPerIndex: 6,
  postPerPage: 6,
  scheduledPostMargin: 15 * 60 * 1000, // 15 minutes
  showArchives: true,
  showBackButton: true,
  editPost: {
    enabled: false,
    text: "Edit page",
    url: "https://github.com/ken-recipe/my-trip-note/edit/main/",
  },
  dynamicOgImage: true,
  dir: "ltr",
  lang: "ja",
  timezone: "Asia/Tokyo",
} as const;
