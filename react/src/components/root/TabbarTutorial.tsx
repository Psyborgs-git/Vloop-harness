import CloseIcon from "@mui/icons-material/Close";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import SearchIcon from "@mui/icons-material/Search";
import SwipeDownIcon from "@mui/icons-material/SwipeDown";
import TouchAppIcon from "@mui/icons-material/TouchApp";
import ViewSidebarIcon from "@mui/icons-material/ViewSidebar";
import {
  Box,
  Button,
  Dialog,
  DialogContent,
  IconButton,
  Stack,
  Typography,
} from "@mui/material";
import type React from "react";
import { useMemo, useState } from "react";

import { getTutorialLocale, tutorialTranslations } from "./tutorialTranslations";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function TabbarTutorial({ open, onClose }: Props) {
  const locale = useMemo(() => getTutorialLocale(), []);
  const t = tutorialTranslations[locale];
  const [step, setStep] = useState(0);
  const steps = [
    {
      icon: <SearchIcon />,
      title: t.searchTitle,
      body: t.searchBody,
      demo: <SearchDemo />,
    },
    {
      icon: <KeyboardArrowUpIcon />,
      title: t.actionsTitle,
      body: t.actionsBody,
      demo: <ActionsDemo />,
    },
    {
      icon: <ViewSidebarIcon />,
      title: t.workspaceTitle,
      body: t.workspaceBody,
      demo: <WorkspaceDemo />,
    },
    {
      icon: <SwipeDownIcon />,
      title: t.panelTitle,
      body: t.panelBody,
      demo: <CloseDemo />,
    },
  ];
  const active = steps[step];

  function finish() {
    setStep(0);
    onClose();
  }

  return (
    <Dialog
      open={open}
      onClose={finish}
      maxWidth="xs"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 2,
          overflow: "hidden",
          border: "1px solid",
          borderColor: "divider",
        },
      }}
    >
      <DialogContent sx={{ p: 0 }}>
        <Box sx={{ p: 2, borderBottom: "1px solid", borderColor: "divider" }}>
          <Stack direction="row" alignItems="flex-start" spacing={1.5}>
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="subtitle1" fontWeight={700}>
                {t.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {t.intro}
              </Typography>
            </Box>
            <IconButton size="small" aria-label={t.skip} onClick={finish}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Box>

        <Box sx={{ p: 2.5 }}>
          <Box
            sx={{
              minHeight: 150,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 1,
              bgcolor: "rgba(255,255,255,0.04)",
              border: "1px solid",
              borderColor: "divider",
              overflow: "hidden",
            }}
          >
            {active.demo}
          </Box>

          <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mt: 2 }}>
            <Box
              sx={{
                width: 34,
                height: 34,
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                color: "primary.main",
                bgcolor: "rgba(99,102,241,0.16)",
                flexShrink: 0,
              }}
            >
              {active.icon}
            </Box>
            <Box>
              <Typography variant="subtitle2" fontWeight={700}>
                {active.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                {active.body}
              </Typography>
            </Box>
          </Stack>

          <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 2.5 }}>
            <Stack direction="row" spacing={0.75} sx={{ flexGrow: 1 }}>
              {steps.map((item, index) => (
                <Box
                  key={item.title}
                  sx={{
                    width: index === step ? 22 : 7,
                    height: 7,
                    borderRadius: 999,
                    bgcolor: index === step ? "primary.main" : "divider",
                    transition: "width 160ms ease, background-color 160ms ease",
                  }}
                />
              ))}
            </Stack>
            <Button size="small" color="inherit" disabled={step === 0} onClick={() => setStep((v) => v - 1)}>
              {t.previous}
            </Button>
            <Button
              size="small"
              variant="contained"
              onClick={() => (step === steps.length - 1 ? finish() : setStep((v) => v + 1))}
            >
              {step === steps.length - 1 ? t.done : t.next}
            </Button>
          </Stack>
        </Box>
      </DialogContent>
    </Dialog>
  );
}

function SearchDemo() {
  return (
    <Box sx={{ position: "relative", width: 230, height: 92 }}>
      <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1 }}>
        <DemoIcon active><SearchIcon fontSize="small" /></DemoIcon>
      </Box>
      <Box
        sx={{
          position: "absolute",
          top: 44,
          right: 0,
          width: 210,
          height: 34,
          borderRadius: 1,
          border: "1px solid",
          borderColor: "primary.main",
          bgcolor: "background.paper",
          animation: "tutorialSearch 2.2s ease-in-out infinite",
          "@keyframes tutorialSearch": {
            "0%, 100%": { transform: "translateY(-8px) scaleX(0.6)", opacity: 0 },
            "25%, 78%": { transform: "translateY(0) scaleX(1)", opacity: 1 },
          },
        }}
      />
      <Finger sx={{ right: 5, top: 8 }} />
    </Box>
  );
}

function ActionsDemo() {
  return (
    <Box sx={{ position: "relative", width: 250, height: 100 }}>
      <DemoIcon active sx={{ mx: "auto" }}><KeyboardArrowUpIcon fontSize="small" /></DemoIcon>
      <Stack
        direction="row"
        spacing={0.75}
        sx={{
          mt: 2,
          justifyContent: "center",
          animation: "tutorialActions 2.2s ease-in-out infinite",
          "@keyframes tutorialActions": {
            "0%, 100%": { opacity: 0, transform: "translateY(14px)" },
            "28%, 82%": { opacity: 1, transform: "translateY(0)" },
          },
        }}
      >
        {["Tools", "Code", "View"].map((label) => (
          <Box
            key={label}
            sx={{
              px: 1,
              py: 0.5,
              borderRadius: 1,
              border: "1px solid",
              borderColor: "divider",
              fontSize: 11,
              color: "text.secondary",
            }}
          >
            {label}
          </Box>
        ))}
      </Stack>
      <Finger sx={{ left: "calc(50% + 12px)", top: 0 }} />
    </Box>
  );
}

function WorkspaceDemo() {
  return (
    <Box sx={{ position: "relative", width: 240, height: 96 }}>
      <Stack direction="row" spacing={1} sx={{ height: 70, mt: 1 }}>
        <Box sx={{ flex: 1, border: "1px solid", borderColor: "divider", borderRadius: 1 }} />
        <Box
          sx={{
            flex: 1.25,
            border: "1px solid",
            borderColor: "primary.main",
            borderRadius: 1,
            animation: "tutorialWorkspace 2.2s ease-in-out infinite",
            "@keyframes tutorialWorkspace": {
              "0%, 100%": { opacity: 0.25, transform: "translateX(-18px)" },
              "28%, 82%": { opacity: 1, transform: "translateX(0)" },
            },
          }}
        />
      </Stack>
      <Finger sx={{ right: 20, top: 10 }} />
    </Box>
  );
}

function CloseDemo() {
  return (
    <Box sx={{ position: "relative", width: 230, height: 96 }}>
      <Box
        sx={{
          width: 150,
          height: 78,
          mx: "auto",
          mt: 1,
          borderRadius: 1,
          border: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
          animation: "tutorialClose 2.2s ease-in-out infinite",
          "@keyframes tutorialClose": {
            "0%, 55%": { opacity: 1, transform: "translateY(0)" },
            "82%, 100%": { opacity: 0, transform: "translateY(24px)" },
          },
        }}
      >
        <KeyboardArrowDownIcon sx={{ display: "block", mx: "auto", mt: 0.5, color: "primary.main" }} />
      </Box>
      <Finger sx={{ left: "50%", top: 12 }} />
    </Box>
  );
}

function DemoIcon({ children, active = false, sx = {} }: { children: React.ReactNode; active?: boolean; sx?: object }) {
  return (
    <Box
      sx={{
        width: 34,
        height: 34,
        borderRadius: "50%",
        display: "grid",
        placeItems: "center",
        color: active ? "primary.contrastText" : "text.secondary",
        bgcolor: active ? "primary.main" : "rgba(255,255,255,0.08)",
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}

function Finger({ sx = {} }: { sx?: object }) {
  return (
    <TouchAppIcon
      sx={{
        position: "absolute",
        color: "primary.light",
        filter: "drop-shadow(0 6px 12px rgba(0,0,0,0.35))",
        animation: "tutorialFinger 2.2s ease-in-out infinite",
        "@keyframes tutorialFinger": {
          "0%, 100%": { transform: "translate(0, 0) scale(1)", opacity: 0.55 },
          "45%": { transform: "translate(-4px, 8px) scale(0.92)", opacity: 1 },
        },
        ...sx,
      }}
    />
  );
}
