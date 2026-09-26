import {test, expect} from '@playwright/test';

const markdown = [
  '## План работы', '', '**Важный шаг** и *пояснение*.', '',
  '- Первый пункт', '- Второй пункт', '',
  '1. Проверить', '2. Запустить', '',
  '> Цитата', '', '`inline_code`', '',
  '```ts', 'const text = "**literal**";', '```', '',
  '| Этап | Статус |', '| --- | --- |', '| Сборка | Готово |', '',
  '[Документация](https://example.com)', '',
  '[Опасная ссылка](javascript:alert(1))', '',
  '<script>window.markdownExecuted = true</script>',
].join('\n');

test('renders saved and new assistant Markdown without executing HTML', async ({page}) => {
  const response = {id:'saved', assistant_text:markdown, tool_calls:[], tool_results:[]};
  await page.route('**/core/api/v1/devices', route => route.fulfill({json:[]}));
  await page.route('**/core/api/v1/assistant/history', route => route.fulfill({json:[
    {...response, user_message:'**Мой текст**', created_at:new Date().toISOString()},
  ]}));
  await page.route('**/core/api/v1/assistant/message', route => route.fulfill({json:{...response,id:'new'}}));
  await page.goto('/');
  await page.getByRole('button',{name:'Assistant',exact:true}).click();
  const message = page.locator('.markdown-message').first();
  await expect(message.getByRole('heading',{name:'План работы',level:2})).toBeVisible();
  await expect(message.locator('strong')).toHaveText('Важный шаг');
  await expect(message.locator('ul > li')).toHaveCount(2);
  await expect(message.locator('ol > li')).toHaveCount(2);
  await expect(message.locator('pre code')).toContainText('"**literal**"');
  await expect(message.getByRole('cell',{name:'Готово'})).toBeVisible();
  await expect(message.getByRole('link',{name:'Документация'})).toHaveAttribute('rel','noopener noreferrer');
  await expect(message.locator('[href^="javascript:"], script')).toHaveCount(0);
  expect(await page.evaluate(() => 'markdownExecuted' in window)).toBe(false);
  await expect(page.locator('.user-message p')).toHaveText('**Мой текст**');
  await page.getByLabel('Сообщение Assistant').fill('Ещё один ответ');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.markdown-message h2')).toHaveCount(2);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
