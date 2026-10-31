import * as Collapsible from "@radix-ui/react-collapsible";
import {
  ChevronDownIcon,
  DownloadIcon,
  FileTextIcon,
  MagnifyingGlassIcon,
  VideoIcon,
} from "@radix-ui/react-icons";
import * as ScrollArea from "@radix-ui/react-scroll-area";
import * as Tabs from "@radix-ui/react-tabs";
import { Badge } from "@radix-ui/themes/components/badge";
import { Button } from "@radix-ui/themes/components/button";
import * as TextField from "@radix-ui/themes/components/text-field";
import { Theme } from "@radix-ui/themes/components/theme";
import {
  createRef,
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal, flushSync } from "react-dom";
import { createRoot } from "react-dom/client";

export type View = "transcript" | "fact-checks" | "corrections" | "pending";
type Counts = Record<View, number>;

const views: { value: View; label: string }[] = [
  { value: "transcript", label: "逐字稿" },
  { value: "fact-checks", label: "事實查核" },
  { value: "corrections", label: "校對紀錄" },
  { value: "pending", label: "待確認" },
];

interface ControlsHandle {
  setView(view: View): void;
  setCounts(counts: Counts): void;
}

interface Mounts {
  page: HTMLElement;
  tabs: HTMLElement;
  search: HTMLElement;
  reset: HTMLElement;
  chapters: HTMLElement;
  tools: HTMLElement;
  chapterPanel: HTMLElement;
  media: HTMLElement;
  downloads: HTMLElement;
  processing: HTMLElement;
}

// React owns controls and wrappers only. The reader keeps ownership of these
// static subtrees, including its rendered cues, native chapters, and iframe.
function ReaderContent({ element }: { element: HTMLElement }) {
  const host = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    host.current?.append(element);
  }, [element]);
  return <div className="engine-content" ref={host} />;
}

function ToolGroup({
  name,
  label,
  element,
  icon,
}: {
  name: "media" | "downloads" | "processing";
  label: string;
  element: HTMLElement;
  icon: typeof VideoIcon;
}) {
  const group = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(
    () => name !== "processing" && window.matchMedia("(max-width: 820px)").matches,
  );
  useLayoutEffect(() => {
    if (name === "processing") return;
    const compact = window.matchMedia("(max-width: 820px)");
    const update = () => {
      setOpen(compact.matches || !!group.current?.contains(document.activeElement));
    };
    compact.addEventListener("change", update);
    return () => compact.removeEventListener("change", update);
  }, [name]);
  const Icon = icon;
  return (
    <Collapsible.Root
      ref={group}
      id={`${name}-tools`}
      className={`tool-group ${name === "processing" ? "provenance" : ""}`}
      open={open}
      onOpenChange={setOpen}
    >
      <Collapsible.Trigger asChild>
        <Button
          id={`${name}-trigger`}
          aria-controls={`${name}-content`}
          className="tool-trigger"
          variant="ghost"
          color="gray"
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
          <ChevronDownIcon aria-hidden="true" className="tool-chevron" />
        </Button>
      </Collapsible.Trigger>
      <Collapsible.Content
        id={`${name}-content`}
        className="tool-content"
        role="region"
        aria-labelledby={`${name}-trigger`}
        forceMount
        hidden={!open}
      >
        <ReaderContent element={element} />
      </Collapsible.Content>
    </Collapsible.Root>
  );
}

const ReaderControls = forwardRef<
  ControlsHandle,
  { mounts: Mounts; onViewChange(view: View): void }
>(function ReaderControls({ mounts, onViewChange }, ref) {
  const [view, setView] = useState<View>("transcript");
  const [counts, setCounts] = useState<Counts>({
    transcript: 0,
    "fact-checks": 0,
    corrections: 0,
    pending: 0,
  });
  useImperativeHandle(ref, () => ({ setView, setCounts }), []);

  useLayoutEffect(() => {
    const header = mounts.page.querySelector<HTMLElement>(".masthead");
    if (!header) return;
    const update = () => {
      document.documentElement.style.setProperty(
        "--header-height",
        `${header.getBoundingClientRect().height}px`,
      );
    };
    const observer = new ResizeObserver(update);
    observer.observe(header);
    update();
    return () => observer.disconnect();
  }, [mounts]);

  return (
    <Theme appearance="light" accentColor="indigo" grayColor="sand" radius="medium">
      <ReaderContent element={mounts.page} />
      {createPortal(
        <Tabs.Root
          value={view}
          onValueChange={(value) => {
            const selected = views.find((item) => item.value === value);
            if (selected) onViewChange(selected.value);
          }}
        >
          <Tabs.List className="tabs" aria-label="紀錄類別">
            {views.map((item) => (
              <Tabs.Trigger
                key={item.value}
                value={item.value}
                id={`tab-${item.value}`}
                aria-controls={`panel-${item.value}`}
                aria-label={`${item.label} ${new Intl.NumberFormat("zh-TW").format(counts[item.value])}`}
                data-view={item.value}
              >
                <span className="tab-label">{item.label}</span>
                <Badge id={`count-${item.value}`} color="gray" variant="soft" size="1">
                  {new Intl.NumberFormat("zh-TW").format(counts[item.value])}
                </Badge>
              </Tabs.Trigger>
            ))}
          </Tabs.List>
        </Tabs.Root>,
        mounts.tabs,
      )}
      {createPortal(
        <TextField.Root
          id="search"
          className="search-box"
          type="search"
          placeholder="輸入關鍵字，尋找發言或查核…"
          autoComplete="off"
          size="3"
          variant="surface"
        >
          <TextField.Slot side="left">
            <MagnifyingGlassIcon aria-hidden="true" width="18" height="18" />
          </TextField.Slot>
          <TextField.Slot side="right">
            <Button id="clear-search" type="button" variant="ghost" size="1">
              清除
            </Button>
          </TextField.Slot>
        </TextField.Root>,
        mounts.search,
      )}
      {createPortal(
        <Button id="reset-filters" type="button" variant="ghost" size="2">
          重設篩選
        </Button>,
        mounts.reset,
      )}
      {createPortal(
        <ScrollArea.Root className="chapter-scroll-area" type="auto">
          <ScrollArea.Viewport className="sidebar-sticky">
            <ReaderContent element={mounts.chapterPanel} />
          </ScrollArea.Viewport>
          <ScrollArea.Scrollbar className="rail-scrollbar" orientation="vertical">
            <ScrollArea.Thumb className="rail-scroll-thumb" />
          </ScrollArea.Scrollbar>
        </ScrollArea.Root>,
        mounts.chapters,
      )}
      {createPortal(
        <>
          <ToolGroup name="media" label="現場影音" element={mounts.media} icon={VideoIcon} />
          <ToolGroup
            name="downloads"
            label="檔案下載"
            element={mounts.downloads}
            icon={DownloadIcon}
          />
          <ToolGroup
            name="processing"
            label="處理資訊與校對方法"
            element={mounts.processing}
            icon={FileTextIcon}
          />
        </>,
        mounts.tools,
      )}
    </Theme>
  );
});

function required(selector: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(selector);
  if (!element) throw new Error(`Required reader control host is missing: ${selector}`);
  return element;
}

export function mountReaderControls(onViewChange: (view: View) => void): ControlsHandle {
  const mounts: Mounts = {
    page: required(".page-shell"),
    tabs: required("#record-tabs"),
    search: required("#search-control"),
    reset: required("#reset-control"),
    chapters: required("#chapter-scroll"),
    tools: required("#tool-controls"),
    chapterPanel: required(".chapter-panel"),
    media: required(".media-panel"),
    downloads: required(".downloads"),
    processing: required(".provenance dl"),
  };
  for (const host of [mounts.tabs, mounts.search, mounts.reset, mounts.chapters, mounts.tools]) {
    host.replaceChildren();
  }
  const root = document.createElement("div");
  root.id = "reader-controls";
  document.body.append(root);
  const ref = createRef<ControlsHandle>();
  flushSync(() =>
    createRoot(root).render(
      <ReaderControls ref={ref} mounts={mounts} onViewChange={onViewChange} />,
    ),
  );
  const controls = ref.current;
  if (!controls) throw new Error("Reader controls did not mount");
  return {
    setView(view) {
      flushSync(() => controls.setView(view));
    },
    setCounts(counts) {
      flushSync(() => controls.setCounts(counts));
    },
  };
}
