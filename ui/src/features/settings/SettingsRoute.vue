<script setup lang="ts">
import { useAppContext } from '@/app/context'
import SettingsPage from './SettingsPage.vue'
const { connection, theme } = useAppContext()
</script>
<template><SettingsPage :connection="connection" :theme="theme" /></template>
