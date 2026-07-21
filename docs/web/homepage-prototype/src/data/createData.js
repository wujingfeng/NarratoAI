import { FilmSlate, Scissors, Translate } from "@phosphor-icons/react";

export const creationTypes = [
  {
    id: "narration",
    titleKey: "create.types.narration.title",
    descriptionKey: "create.types.narration.description",
    icon: FilmSlate,
    tone: "violet",
    maxVideos: 5,
  },
  {
    id: "translation",
    titleKey: "create.types.translation.title",
    descriptionKey: "create.types.translation.description",
    icon: Translate,
    tone: "cyan",
    maxVideos: 1,
  },
  {
    id: "remix",
    titleKey: "create.types.remix.title",
    descriptionKey: "create.types.remix.description",
    icon: Scissors,
    tone: "orange",
    maxVideos: 10,
  },
];

export const initialCreateVideos = [
  {
    id: "demo-episode-1",
    name: "第 1 集.mp4",
    durationSeconds: 201,
    durationLabel: "03:21",
    subtitleStatusKey: "create.subtitle.matched",
    statusTone: "success",
    subtitleName: "第1集.srt",
    thumbnail: "/assets/short-drama-thumb.webp",
  },
  {
    id: "demo-episode-2",
    name: "第 2 集.mp4",
    durationSeconds: 178,
    durationLabel: "02:58",
    subtitleStatusKey: "create.subtitle.aiRecognition",
    statusTone: "warning",
    subtitleName: null,
    thumbnail: "/assets/film-action-thumb.webp",
  },
  {
    id: "demo-episode-3",
    name: "第 3 集.mp4",
    durationSeconds: 143,
    durationLabel: "02:23",
    subtitleStatusKey: "create.subtitle.aiRecognition",
    statusTone: "warning",
    subtitleName: null,
    thumbnail: "/assets/documentary-thumb.webp",
  },
];
